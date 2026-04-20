"""Signal-to-order bridge — translate Inverse HUNTER + cycle signals
into paper-trading order instructions.

Does NOT execute orders directly (no broker connection built-in — you
choose). Instead, produces a standardised order instruction list that
you can either:
  (a) Execute manually on your IB paper account
  (b) Feed into an IB API script later
  (c) Use as an audit log for what HUNTER would have traded

Output: JSON instruction file per day, plus a readable markdown log.

Run:
    python signal_to_order.py today              # generate today's orders
    python signal_to_order.py pending            # list open orders awaiting action
    python signal_to_order.py audit              # show all order history
"""

import json
import sys
from datetime import datetime
from pathlib import Path

from database import get_connection


HERE = Path(__file__).parent
ORDERS_DIR = HERE / "orders"


def _ensure_dirs():
    ORDERS_DIR.mkdir(parents=True, exist_ok=True)


# Default per-signal capital allocation
CAPITAL_PER_SIGNAL_GBP = 1000
MAX_CAPITAL_PER_DAY_GBP = 10000


# ══════════════════════════════════════════════════════════════════════
# Pull eligible signals
# ══════════════════════════════════════════════════════════════════════

def _inverse_orders() -> list:
    conn = get_connection()
    try:
        # Check if inverse_signals table exists
        exists = conn.execute("""
            SELECT COUNT(*) FROM sqlite_master
            WHERE type='table' AND name='inverse_signals'
        """).fetchone()[0]
        if not exists:
            return []
        rows = conn.execute("""
            SELECT s.id, s.asset, s.signal_direction, s.signal_strength,
                   s.contradiction_score, s.assumption_claim, s.reasoning,
                   b.belief_text, b.target_date
            FROM inverse_signals s
            LEFT JOIN market_beliefs b ON b.id = s.belief_id
            WHERE s.status = 'open' AND s.contradiction_score >= 0.65
            ORDER BY s.contradiction_score DESC
        """).fetchall()
    finally:
        conn.close()
    out = []
    for r in rows:
        sid, asset, direction, strength, score, claim, reasoning, belief_text, target_date = r
        if not asset or asset == "MANUAL":
            continue
        size = CAPITAL_PER_SIGNAL_GBP
        if strength == "moderate":
            size = int(CAPITAL_PER_SIGNAL_GBP * 0.6)
        elif strength == "weak":
            continue
        out.append({
            "source": "inverse_hunter",
            "signal_id": sid,
            "ticker": asset,
            "direction": direction,
            "size_gbp": size,
            "target_close_date": target_date,
            "reasoning": (reasoning or "")[:200],
            "trigger_belief": (belief_text or "")[:200],
            "strength": strength,
            "score": score,
        })
    return out


def _cycle_orders() -> list:
    conn = get_connection()
    try:
        exists = conn.execute("""
            SELECT COUNT(*) FROM sqlite_master
            WHERE type='table' AND name='cycle_positions'
        """).fetchone()[0]
        if not exists:
            return []
        rows = conn.execute("""
            SELECT cp.id, cp.cycle_id, cp.ib_ticker, cp.proposed_direction,
                   cp.proposed_capital_gbp, cp.target_exit_date, cp.node_domain
            FROM cycle_positions cp
            WHERE cp.status = 'planned'
        """).fetchall()
    finally:
        conn.close()
    out = []
    for r in rows:
        pid, cid, ticker, direction, capital, target_exit, domain = r
        if not ticker:
            continue
        out.append({
            "source": "cycle_portfolio",
            "cycle_position_id": pid,
            "cycle_id": cid,
            "ticker": ticker,
            "direction": direction,
            "size_gbp": capital,
            "target_close_date": target_exit,
            "reasoning": f"Part of detected cycle #{cid} — node: {domain}",
            "trigger_belief": "Framework Layer 8: cycle persistence",
            "strength": "moderate",
            "score": 0.5,
        })
    return out


# ══════════════════════════════════════════════════════════════════════
# Daily order generation
# ══════════════════════════════════════════════════════════════════════

def generate_today_orders() -> dict:
    _ensure_dirs()
    today = datetime.now().strftime("%Y-%m-%d")

    inverse = _inverse_orders()
    cycle = _cycle_orders()
    all_orders = inverse + cycle

    # Cap at MAX_CAPITAL_PER_DAY_GBP
    all_orders.sort(key=lambda o: -o["score"])
    running_total = 0
    approved = []
    deferred = []
    for o in all_orders:
        if running_total + o["size_gbp"] <= MAX_CAPITAL_PER_DAY_GBP:
            approved.append(o)
            running_total += o["size_gbp"]
        else:
            deferred.append(o)

    # Write JSON
    json_path = ORDERS_DIR / f"{today}_orders.json"
    payload = {
        "generated_at": datetime.now().isoformat(),
        "approved_orders": approved,
        "deferred_orders": deferred,
        "total_capital_gbp": running_total,
        "cap_gbp": MAX_CAPITAL_PER_DAY_GBP,
    }
    json_path.write_text(json.dumps(payload, indent=2))

    # Write markdown
    md_path = ORDERS_DIR / f"{today}_orders.md"
    lines = [
        f"# HUNTER orders — {today}\n",
        f"*Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}. Capital deployed: £{running_total:,} / £{MAX_CAPITAL_PER_DAY_GBP:,} cap.*\n",
        "\n## Approved orders\n",
        "| # | Ticker | Dir | Size | Source | Target close | Reasoning |",
        "|---|---|---|---|---|---|---|",
    ]
    for i, o in enumerate(approved, 1):
        arrow = "↑ LONG" if o["direction"] == "long" else "↓ SHORT"
        lines.append(
            f"| {i} | **{o['ticker']}** | {arrow} | £{o['size_gbp']:,} | "
            f"{o['source']} | {o.get('target_close_date') or '?'} | {o['reasoning'][:80]} |"
        )
    if deferred:
        lines.append("\n## Deferred (over daily cap)\n")
        for o in deferred[:10]:
            lines.append(f"- {o['ticker']} {o['direction']} £{o['size_gbp']:,} ({o['source']})")
    lines.append("\n---\n\n**To execute**: copy each approved ticker + direction + size into your IB paper account. Set the target close date as a calendar reminder.")
    md_path.write_text("\n".join(lines))

    return {
        "orders_written": len(approved),
        "deferred": len(deferred),
        "total_gbp": running_total,
        "json_path": str(json_path),
        "md_path": str(md_path),
    }


def pending():
    _ensure_dirs()
    files = sorted(ORDERS_DIR.glob("*_orders.json"), reverse=True)
    if not files:
        print("No orders generated yet.")
        return
    for f in files[:7]:
        data = json.loads(f.read_text())
        print(f"\n{f.name}: {len(data['approved_orders'])} approved, "
              f"{len(data['deferred_orders'])} deferred, £{data['total_capital_gbp']:,}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "today"

    if cmd == "today":
        r = generate_today_orders()
        print(f"\n✓ {r['orders_written']} orders written to:")
        print(f"   {r['json_path']}")
        print(f"   {r['md_path']}")
        print(f"\n   Deferred: {r['deferred']}")
        print(f"   Total capital: £{r['total_gbp']:,}")

    elif cmd == "pending":
        pending()

    elif cmd == "audit":
        _ensure_dirs()
        files = sorted(ORDERS_DIR.glob("*_orders.json"))
        total_approved = 0
        for f in files:
            data = json.loads(f.read_text())
            total_approved += len(data.get("approved_orders", []))
        print(f"\nTotal order files: {len(files)}")
        print(f"Total approved orders (historic): {total_approved}")
    else:
        print(__doc__)
