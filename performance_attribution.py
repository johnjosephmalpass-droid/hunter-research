"""Performance attribution — separate P&L by portfolio type.

HUNTER now runs THREE parallel portfolios:
  1. Thesis portfolio  — positions from surviving hypotheses (portfolio.py)
  2. Cycle portfolio   — coordinated positions at cycle nodes (cycle_portfolio.py)
  3. Inverse portfolio — short positions from Inverse HUNTER signals

Each has a different theoretical basis. Attributing P&L separately lets
us test WHICH mechanism actually produces alpha. That matters for both
the research paper and the commercial path.

Output: per-portfolio stats + combined weighted performance.

Run:
    python performance_attribution.py          # basic attribution
    python performance_attribution.py json     # machine-readable
    python performance_attribution.py weekly   # compare last 7 days
"""

import json
import sys
from datetime import datetime, timedelta

from database import get_connection


def _portfolio_stats():
    conn = get_connection()
    try:
        # Thesis portfolio
        thesis_open = conn.execute("""
            SELECT COUNT(*), COALESCE(SUM(pnl_pct * capital_allocated) / SUM(capital_allocated), 0) AS weighted_pnl
            FROM portfolio_positions
            WHERE status = 'open' AND ticker != 'LOGGED'
        """).fetchone()
        thesis_closed = conn.execute("""
            SELECT COUNT(*),
                   COALESCE(AVG(pnl_pct), 0),
                   COALESCE(SUM(CASE WHEN pnl_pct > 0 THEN 1 ELSE 0 END), 0) as wins
            FROM portfolio_positions
            WHERE status = 'closed' AND ticker != 'LOGGED'
        """).fetchone()

        # Cycle portfolio
        cycle_open_exists = conn.execute("""
            SELECT COUNT(*) FROM sqlite_master
            WHERE type='table' AND name='cycle_positions'
        """).fetchone()[0]

        if cycle_open_exists:
            cycle_open = conn.execute("""
                SELECT COUNT(*), COALESCE(AVG(pnl_pct), 0)
                FROM cycle_positions WHERE status = 'open'
            """).fetchone()
            cycle_closed = conn.execute("""
                SELECT COUNT(*), COALESCE(AVG(pnl_pct), 0),
                       COALESCE(SUM(CASE WHEN pnl_pct > 0 THEN 1 ELSE 0 END), 0) as wins
                FROM cycle_positions WHERE status = 'closed'
            """).fetchone()
        else:
            cycle_open = (0, 0)
            cycle_closed = (0, 0, 0)

        # Inverse signals (no actual P&L yet unless resolved)
        inverse_exists = conn.execute("""
            SELECT COUNT(*) FROM sqlite_master
            WHERE type='table' AND name='inverse_signals'
        """).fetchone()[0]
        if inverse_exists:
            inv_open = conn.execute("""
                SELECT COUNT(*) FROM inverse_signals WHERE status = 'open'
            """).fetchone()[0]
            inv_resolved = conn.execute("""
                SELECT COUNT(*),
                       COALESCE(SUM(CASE WHEN resolution_correct = 1 THEN 1 ELSE 0 END), 0) as correct
                FROM inverse_signals WHERE status IN ('resolved', 'closed')
            """).fetchone()
        else:
            inv_open = 0
            inv_resolved = (0, 0)
    finally:
        conn.close()

    thesis_count, thesis_closed_avg, thesis_wins = thesis_closed
    cycle_count, cycle_closed_avg, cycle_wins = cycle_closed
    inv_resolved_count, inv_correct = inv_resolved

    return {
        "thesis": {
            "open_positions": thesis_open[0],
            "open_weighted_pnl_pct": round(thesis_open[1] or 0, 2),
            "closed_count": thesis_count,
            "closed_avg_pnl_pct": round(thesis_closed_avg, 2),
            "closed_win_rate": round(thesis_wins / max(1, thesis_count), 3),
        },
        "cycle": {
            "open_positions": cycle_open[0],
            "open_avg_pnl_pct": round(cycle_open[1] or 0, 2),
            "closed_count": cycle_count,
            "closed_avg_pnl_pct": round(cycle_closed_avg, 2),
            "closed_win_rate": round(cycle_wins / max(1, cycle_count), 3),
        },
        "inverse": {
            "open_signals": inv_open,
            "resolved_count": inv_resolved_count,
            "hit_rate": round(inv_correct / max(1, inv_resolved_count), 3),
        },
    }


def _combined_alpha() -> dict:
    """Combined risk-weighted alpha across all three portfolios. Placeholder
    for now — full implementation would fetch SPY return over the same window
    and subtract it from each portfolio's return."""
    stats = _portfolio_stats()
    # Simple weighted blend: average of the three closed-P&L figures, weighted by count
    weights = {
        "thesis": stats["thesis"]["closed_count"],
        "cycle": stats["cycle"]["closed_count"],
        "inverse": stats["inverse"]["resolved_count"],
    }
    pnls = {
        "thesis": stats["thesis"]["closed_avg_pnl_pct"],
        "cycle": stats["cycle"]["closed_avg_pnl_pct"],
        "inverse": stats["inverse"]["hit_rate"] * 100 - 50,  # rough signal proxy
    }
    total_weight = sum(weights.values())
    if total_weight == 0:
        return {"combined_weighted_pnl": 0, "contributing_portfolios": 0}
    blended = sum(pnls[k] * weights[k] for k in pnls) / total_weight
    return {
        "combined_weighted_pnl": round(blended, 2),
        "contributing_portfolios": sum(1 for w in weights.values() if w > 0),
        "weights": weights,
    }


def attribution_report() -> dict:
    return {
        "generated_at": datetime.now().isoformat(),
        "portfolios": _portfolio_stats(),
        "combined": _combined_alpha(),
    }


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "print"
    r = attribution_report()
    if cmd == "json":
        print(json.dumps(r, indent=2, default=str))
    else:
        print(f"\nHUNTER PERFORMANCE ATTRIBUTION  {r['generated_at'][:19]}")
        print("=" * 70)
        for name, p in r["portfolios"].items():
            print(f"\n{name.upper()} PORTFOLIO")
            for k, v in p.items():
                print(f"  {k:<30} {v}")
        print(f"\nCOMBINED")
        for k, v in r["combined"].items():
            print(f"  {k:<30} {v}")
        print()
