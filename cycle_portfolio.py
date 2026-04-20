"""Cycle Portfolio — trade the detected epistemic cycles directly.

The framework claims cycles are STABLE EQUILIBRIA — reinforcement ≥ correction
at each node, so the cycle persists for its estimated window. That's a
falsifiable prediction AND a trading strategy in one.

For each detected cycle in `detected_cycles`:
  1. Map each node (canonicalised methodology/assumption) to one asset.
  2. Compute per-node exposure direction from the cycle's reinforcement pattern.
  3. Open coordinated positions across ALL nodes simultaneously.
  4. Hold through the persistence_estimate window (or exit early on correction).
  5. Record P&L attributed to the cycle as a whole, not to individual nodes.

Why this is different from normal portfolio:
  - Normal: bets on a single thesis.
  - Cycle: bets on the STRUCTURE. If any one node moves wrong but the cycle
    as a whole is intact, you're still right.
  - A cycle portfolio's P&L directly tests the framework's Layer 8 claim.

Usage:
    python cycle_portfolio.py plan            # show proposed positions per cycle
    python cycle_portfolio.py open            # open paper positions for new cycles
    python cycle_portfolio.py review          # check which cycles are still active
    python cycle_portfolio.py close_expired   # close positions past persistence window
    python cycle_portfolio.py audit           # full report of cycle positions + P&L
"""

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

from database import get_connection

load = __import__("dotenv").load_dotenv
load(override=True)


CYCLE_CAPITAL_PER_NODE_GBP = 2000      # GBP per node per cycle
MIN_REINFORCEMENT_TO_OPEN = 0.5        # strength threshold
DEFAULT_HOLD_DAYS = 45                 # fallback if persistence estimate missing


# ══════════════════════════════════════════════════════════════════════
# Schema
# ══════════════════════════════════════════════════════════════════════

def _ensure_tables():
    conn = get_connection()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS cycle_positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cycle_id INTEGER REFERENCES detected_cycles(id),
                node_index INTEGER,
                node_domain TEXT,
                node_methodology TEXT,
                proposed_asset TEXT,
                proposed_direction TEXT,
                proposed_capital_gbp REAL,
                status TEXT DEFAULT 'planned',
                ib_ticker TEXT,
                entry_price REAL,
                entry_date TEXT,
                target_exit_date TEXT,
                current_price REAL,
                pnl_pct REAL DEFAULT 0.0,
                close_date TEXT,
                close_reason TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_cycle_positions_cycle ON cycle_positions(cycle_id);
            CREATE INDEX IF NOT EXISTS idx_cycle_positions_status ON cycle_positions(status);

            CREATE TABLE IF NOT EXISTS cycle_outcomes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cycle_id INTEGER REFERENCES detected_cycles(id),
                opened_date TEXT,
                closed_date TEXT,
                total_pnl_pct REAL,
                nodes_winning INTEGER,
                nodes_losing INTEGER,
                cycle_persisted_as_predicted INTEGER,
                notes TEXT
            );
        """)
        conn.commit()
    finally:
        conn.close()


# ══════════════════════════════════════════════════════════════════════
# Mapping cycle nodes → tradeable assets
# ══════════════════════════════════════════════════════════════════════

# A pragmatic domain → liquid-proxy-asset map. Edit for your use case.
DOMAIN_ASSET_MAP = {
    "cre_credit":                  {"long_proxy": "IYR",  "short_proxy": "SRS",  "note": "REIT sector"},
    "commercial real estate":      {"long_proxy": "IYR",  "short_proxy": "SRS",  "note": "REIT sector"},
    "cmbs":                        {"long_proxy": "CMBS", "short_proxy": "TLT",  "note": "CMBS ETF"},
    "structured finance":          {"long_proxy": "CMBS", "short_proxy": "TLT",  "note": "Structured credit"},
    "credit rating":               {"long_proxy": "LQD",  "short_proxy": "HYG",  "note": "IG vs HY"},
    "insurance":                   {"long_proxy": "IAK",  "short_proxy": "MET",  "note": "Insurance sector"},
    "insurance and pension":       {"long_proxy": "IAK",  "short_proxy": "MET",  "note": "Insurance sector"},
    "fixed income":                {"long_proxy": "AGG",  "short_proxy": "TLT",  "note": "Agg bond"},
    "pension":                     {"long_proxy": "PBJ",  "short_proxy": "TLT",  "note": "Pension-exposed"},
    "real estate appraisal":       {"long_proxy": "IYR",  "short_proxy": "SRS",  "note": "REIT appraisal"},
    "steel":                       {"long_proxy": "SLX",  "short_proxy": "CLF",  "note": "Steel sector"},
    "energy":                      {"long_proxy": "XLE",  "short_proxy": "ERY",  "note": "Energy sector"},
    "pharmaceutical":              {"long_proxy": "IHE",  "short_proxy": "PFE",  "note": "Pharma sector"},
    "healthcare":                  {"long_proxy": "XLV",  "short_proxy": "MOH",  "note": "Healthcare"},
    "bankruptcy":                  {"long_proxy": "DBC",  "short_proxy": "HYG",  "note": "Distressed exposure"},
    "regulation":                  {"long_proxy": "SPY",  "short_proxy": "EPU",  "note": "Regulatory-exposed"},
    "unknown":                     {"long_proxy": "SPY",  "short_proxy": "SH",   "note": "Default"},
}


def _match_asset(domain_text: str) -> dict:
    """Fuzzy match a domain description to an asset proxy."""
    if not domain_text:
        return DOMAIN_ASSET_MAP["unknown"]
    lower = domain_text.lower()
    for key, mapping in DOMAIN_ASSET_MAP.items():
        if key in lower:
            return mapping
    return DOMAIN_ASSET_MAP["unknown"]


def _propose_direction(cycle: dict, node_index: int) -> str:
    """Direction logic: odd-indexed nodes take the opposite side of even-indexed.
    Refined later per-cycle. For now: alternating long/short to create a market-neutral cycle bet."""
    # Simple rule: first half long, second half short. This creates pair-style exposure.
    try:
        nodes = json.loads(cycle.get("nodes") or "[]")
    except json.JSONDecodeError:
        return "long"
    half = len(nodes) // 2
    return "long" if node_index < half else "short"


# ══════════════════════════════════════════════════════════════════════
# Planning — no trades executed, just proposed positions
# ══════════════════════════════════════════════════════════════════════

def plan_positions_for_cycle(cycle_id: int) -> list:
    conn = get_connection()
    try:
        row = conn.execute("""
            SELECT id, cycle_type, nodes, domains, reinforcement_strength,
                   persistence_estimate, detected_date, is_active
            FROM detected_cycles WHERE id = ?
        """, (cycle_id,)).fetchone()
    finally:
        conn.close()
    if not row:
        return []
    cycle = dict(zip(
        ["id", "cycle_type", "nodes", "domains", "reinforcement_strength",
         "persistence_estimate", "detected_date", "is_active"], row))

    try:
        nodes = json.loads(cycle.get("nodes") or "[]")
    except json.JSONDecodeError:
        return []

    if cycle.get("reinforcement_strength", 0) < MIN_REINFORCEMENT_TO_OPEN:
        return []

    pe = cycle.get("persistence_estimate") or DEFAULT_HOLD_DAYS
    hold_days = max(14, min(180, int(pe)))

    proposed = []
    for i, n in enumerate(nodes):
        domain = n.get("domain", "unknown") if isinstance(n, dict) else "unknown"
        meth = n.get("methodology", "") if isinstance(n, dict) else ""
        direction = _propose_direction(cycle, i)
        asset_map = _match_asset(domain)
        ticker = asset_map["long_proxy"] if direction == "long" else asset_map["short_proxy"]
        proposed.append({
            "cycle_id": cycle_id,
            "node_index": i,
            "node_domain": domain,
            "node_methodology": meth[:200],
            "proposed_asset": ticker,
            "proposed_direction": direction,
            "proposed_capital_gbp": CYCLE_CAPITAL_PER_NODE_GBP,
            "hold_days": hold_days,
            "asset_note": asset_map["note"],
        })
    return proposed


def plan_all_new_cycles() -> dict:
    """Propose positions for every cycle that doesn't yet have them."""
    conn = get_connection()
    try:
        new_cycles = conn.execute("""
            SELECT c.id FROM detected_cycles c
            LEFT JOIN cycle_positions p ON p.cycle_id = c.id
            WHERE p.id IS NULL AND c.is_active = 1
              AND c.reinforcement_strength >= ?
        """, (MIN_REINFORCEMENT_TO_OPEN,)).fetchall()
    finally:
        conn.close()

    all_planned = []
    for (cid,) in new_cycles:
        all_planned.extend(plan_positions_for_cycle(cid))
    return {"cycles_planned": len(new_cycles), "positions_planned": len(all_planned),
            "details": all_planned}


# ══════════════════════════════════════════════════════════════════════
# Open (paper) — writes to cycle_positions with status='open'
# ══════════════════════════════════════════════════════════════════════

def open_positions_for_cycle(cycle_id: int, use_yfinance_price: bool = True) -> int:
    positions = plan_positions_for_cycle(cycle_id)
    if not positions:
        return 0
    conn = get_connection()
    try:
        # Fetch hold_days from first position's plan
        conn.execute("SELECT persistence_estimate FROM detected_cycles WHERE id = ?",
                     (cycle_id,))
        for p in positions:
            entry_date = datetime.now().strftime("%Y-%m-%d")
            target_exit_date = (datetime.now() + timedelta(days=p["hold_days"])).strftime("%Y-%m-%d")
            entry_price = None
            if use_yfinance_price:
                try:
                    import yfinance as yf
                    tkr = yf.Ticker(p["proposed_asset"])
                    hist = tkr.history(period="5d")
                    if not hist.empty:
                        entry_price = float(hist["Close"].iloc[-1])
                except Exception:
                    pass
            conn.execute("""
                INSERT INTO cycle_positions
                (cycle_id, node_index, node_domain, node_methodology,
                 proposed_asset, proposed_direction, proposed_capital_gbp,
                 status, ib_ticker, entry_price, entry_date, target_exit_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'open', ?, ?, ?, ?)
            """, (cycle_id, p["node_index"], p["node_domain"], p["node_methodology"],
                  p["proposed_asset"], p["proposed_direction"], p["proposed_capital_gbp"],
                  p["proposed_asset"], entry_price, entry_date, target_exit_date))
        conn.commit()
    finally:
        conn.close()
    return len(positions)


def open_all_new():
    """Open paper positions for every new cycle."""
    conn = get_connection()
    try:
        new_cycles = conn.execute("""
            SELECT c.id FROM detected_cycles c
            LEFT JOIN cycle_positions p ON p.cycle_id = c.id
            WHERE p.id IS NULL AND c.is_active = 1
              AND c.reinforcement_strength >= ?
        """, (MIN_REINFORCEMENT_TO_OPEN,)).fetchall()
    finally:
        conn.close()
    total = 0
    for (cid,) in new_cycles:
        total += open_positions_for_cycle(cid)
    return total


# ══════════════════════════════════════════════════════════════════════
# Review, close, audit
# ══════════════════════════════════════════════════════════════════════

def close_expired():
    conn = get_connection()
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        rows = conn.execute("""
            SELECT id, ib_ticker, proposed_direction, entry_price
            FROM cycle_positions
            WHERE status = 'open' AND target_exit_date <= ?
        """, (today,)).fetchall()
        closed_count = 0
        for r in rows:
            pid, ticker, direction, entry_price = r
            close_price = None
            try:
                import yfinance as yf
                hist = yf.Ticker(ticker).history(period="5d")
                if not hist.empty:
                    close_price = float(hist["Close"].iloc[-1])
            except Exception:
                pass
            pnl_pct = 0.0
            if entry_price and close_price:
                if direction == "long":
                    pnl_pct = (close_price / entry_price - 1) * 100
                else:
                    pnl_pct = (entry_price / close_price - 1) * 100
            conn.execute("""
                UPDATE cycle_positions
                SET status = 'closed', close_date = ?, current_price = ?,
                    pnl_pct = ?, close_reason = 'target_exit_date_reached'
                WHERE id = ?
            """, (today, close_price, pnl_pct, pid))
            closed_count += 1
        conn.commit()
        return closed_count
    finally:
        conn.close()


def update_open_prices():
    """Refresh current_price and pnl_pct for all open positions."""
    try:
        import yfinance as yf
    except ImportError:
        return 0
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT id, ib_ticker, proposed_direction, entry_price
            FROM cycle_positions WHERE status = 'open'
        """).fetchall()
        updated = 0
        for r in rows:
            pid, ticker, direction, entry_price = r
            try:
                hist = yf.Ticker(ticker).history(period="5d")
                if hist.empty or not entry_price:
                    continue
                cp = float(hist["Close"].iloc[-1])
                if direction == "long":
                    pnl = (cp / entry_price - 1) * 100
                else:
                    pnl = (entry_price / cp - 1) * 100
                conn.execute("""
                    UPDATE cycle_positions
                    SET current_price = ?, pnl_pct = ?
                    WHERE id = ?
                """, (cp, pnl, pid))
                updated += 1
            except Exception:
                continue
        conn.commit()
        return updated
    finally:
        conn.close()


def audit():
    conn = get_connection()
    try:
        total_open = conn.execute(
            "SELECT COUNT(*) FROM cycle_positions WHERE status='open'").fetchone()[0]
        total_closed = conn.execute(
            "SELECT COUNT(*) FROM cycle_positions WHERE status='closed'").fetchone()[0]
        avg_pnl = conn.execute(
            "SELECT AVG(pnl_pct) FROM cycle_positions WHERE status='closed'").fetchone()[0] or 0.0
        wins = conn.execute(
            "SELECT COUNT(*) FROM cycle_positions WHERE status='closed' AND pnl_pct > 0").fetchone()[0]
        per_cycle = conn.execute("""
            SELECT cycle_id,
                   COUNT(*) as n_positions,
                   SUM(CASE WHEN status='open' THEN 1 ELSE 0 END) as n_open,
                   AVG(pnl_pct) as avg_pnl
            FROM cycle_positions
            GROUP BY cycle_id
        """).fetchall()
    finally:
        conn.close()
    return {
        "total_open_positions": total_open,
        "total_closed_positions": total_closed,
        "avg_realised_pnl_pct": round(avg_pnl, 2),
        "win_rate": round(wins / max(1, total_closed), 3),
        "per_cycle": [
            {"cycle_id": r[0], "positions": r[1], "open": r[2], "avg_pnl_pct": round(r[3] or 0, 2)}
            for r in per_cycle
        ],
    }


# ══════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    _ensure_tables()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "plan"

    if cmd == "plan":
        r = plan_all_new_cycles()
        print(f"\nProposed positions for {r['cycles_planned']} new cycles "
              f"({r['positions_planned']} positions total)\n")
        for p in r["details"]:
            arrow = "↑" if p["proposed_direction"] == "long" else "↓"
            print(f"  Cycle {p['cycle_id']:>3} node {p['node_index']}: "
                  f"{p['proposed_asset']:<6} {arrow} "
                  f"GBP {p['proposed_capital_gbp']:,.0f}  "
                  f"({p['node_domain'][:40]})")

    elif cmd == "open":
        n = open_all_new()
        print(f"✓ Opened {n} cycle positions (paper).")

    elif cmd == "review":
        n = update_open_prices()
        print(f"Updated prices on {n} open cycle positions.")

    elif cmd == "close_expired":
        n = close_expired()
        print(f"Closed {n} cycle positions past target_exit_date.")

    elif cmd == "audit":
        r = audit()
        print(f"\nCycle Portfolio Audit")
        print(f"  Open:   {r['total_open_positions']}")
        print(f"  Closed: {r['total_closed_positions']}")
        print(f"  Avg realised P&L: {r['avg_realised_pnl_pct']:+.2f}%")
        print(f"  Win rate: {r['win_rate']:.1%}")
        print(f"\nPer-cycle:")
        for pc in r["per_cycle"]:
            print(f"  Cycle {pc['cycle_id']:>3}: {pc['positions']} positions, "
                  f"{pc['open']} open, avg P&L {pc['avg_pnl_pct']:+.2f}%")

    else:
        print(__doc__)
