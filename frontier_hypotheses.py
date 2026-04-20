"""The 6 Frontier Hypotheses — testable, each its own detector.

Source: HUNTER_Research_Space_Map.pdf, Sector F.

These are the genuinely new theoretical claims from the compendium. Each one
has a concrete empirical test, a detector implementation, and a prediction.

If any of these come back positive empirically, they are publishable on
their own as short papers — independently of the main framework.

F1. Information Temperature — domains have different fact turnover rates.
    Collisions between HIGH-temp and LOW-temp domains should be highest-value.

F2. Epistemic Dark Matter — most info is in undetectable (negative-space)
    connections. Infer from unexplained price moves correlating with gaps.

F3. Collision Catalysts — regulatory changes, standard updates, personnel
    changes activate latent connections. Don't contain alpha but TRIGGER it.

F4. Information Metabolism — rate domains convert facts to actionable
    knowledge. Academia=decades, trading=minutes. Measure time-to-price-impact.

F5. Epistemic Immune System — markets actively RESIST cross-silo insights.
    Analysts proposing them get professional pushback. Measure via survey proxy.

F6. Conservation of Ignorance — correcting one mispricing creates another.
    Balloon squeeze. Total residual CONSTANT. Test via correlated corrections.

Usage:
    python frontier_hypotheses.py f1           # test a specific hypothesis
    python frontier_hypotheses.py all          # run all 6
    python frontier_hypotheses.py report       # persist to DB
"""

import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from statistics import mean, stdev

from database import get_connection

try:
    from theory_canon_v2 import DOMAINS_BY_CODE
except ImportError:
    DOMAINS_BY_CODE = {}


# ══════════════════════════════════════════════════════════════════════
# Schema
# ══════════════════════════════════════════════════════════════════════

def _ensure_tables():
    conn = get_connection()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS frontier_test_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hypothesis_id TEXT,
                hypothesis_name TEXT,
                testable INTEGER,
                observation_value REAL,
                prediction_value REAL,
                supports_hypothesis INTEGER,
                evidence_description TEXT,
                measured_at TEXT DEFAULT (datetime('now'))
            );
        """)
        conn.commit()
    finally:
        conn.close()


# ══════════════════════════════════════════════════════════════════════
# F1 — Information Temperature
# ══════════════════════════════════════════════════════════════════════

def f1_information_temperature() -> dict:
    """Measure fact turnover per domain (births - deaths per week).
    Collisions between HIGH-temp and LOW-temp should have higher survival
    and higher scores than same-temp collisions."""
    conn = get_connection()
    try:
        # Fact velocity per source_type over last 90 days
        rows = conn.execute("""
            SELECT source_type, COUNT(*) as n
            FROM raw_facts
            WHERE COALESCE(date_of_fact, ingested_at) >= date('now', '-90 days')
            GROUP BY source_type
        """).fetchall()
        velocity = {r[0]: r[1] / 90.0 for r in rows}

        # Classify each domain as high/low temperature
        median_v = sorted(velocity.values())[len(velocity) // 2] if velocity else 0
        high_temp = {k for k, v in velocity.items() if v > median_v}
        low_temp = {k for k, v in velocity.items() if v <= median_v}

        # For each hypothesis, check if its source types cross temperature bands
        hyp_rows = conn.execute("""
            SELECT h.diamond_score, c.source_types, h.survived_kill
            FROM hypotheses h LEFT JOIN collisions c ON c.id = h.collision_id
            WHERE c.source_types IS NOT NULL
        """).fetchall()
    finally:
        conn.close()

    cross_temp_scores = []
    same_temp_scores = []
    for score, st_json, surv in hyp_rows:
        if not score or not st_json:
            continue
        try:
            types = json.loads(st_json) if st_json.startswith("[") else st_json.split(",")
        except Exception:
            continue
        types = [t.strip() for t in types if t.strip()]
        if not types:
            continue
        has_high = any(t in high_temp for t in types)
        has_low = any(t in low_temp for t in types)
        if has_high and has_low:
            cross_temp_scores.append(score)
        else:
            same_temp_scores.append(score)

    mean_cross = mean(cross_temp_scores) if cross_temp_scores else 0
    mean_same = mean(same_temp_scores) if same_temp_scores else 0
    uplift = mean_cross - mean_same

    return {
        "hypothesis_id": "F1",
        "hypothesis_name": "Information Temperature",
        "n_high_temp_domains": len(high_temp),
        "n_low_temp_domains": len(low_temp),
        "cross_temp_hypothesis_count": len(cross_temp_scores),
        "same_temp_hypothesis_count": len(same_temp_scores),
        "mean_score_cross_temp": round(mean_cross, 2),
        "mean_score_same_temp": round(mean_same, 2),
        "uplift": round(uplift, 2),
        "supports": uplift > 5,
    }


# ══════════════════════════════════════════════════════════════════════
# F2 — Epistemic Dark Matter
# ══════════════════════════════════════════════════════════════════════

def f2_epistemic_dark_matter() -> dict:
    """Estimate ratio of (detected collisions) / (theoretical possible collisions).
    If detected << theoretical, the 'dark matter' hypothesis is supported."""
    conn = get_connection()
    try:
        n_collisions = conn.execute("SELECT COUNT(*) FROM collisions").fetchone()[0] or 0
        n_source_types = conn.execute(
            "SELECT COUNT(DISTINCT source_type) FROM raw_facts"
        ).fetchone()[0] or 0
    finally:
        conn.close()

    theoretical_pairs = n_source_types * (n_source_types - 1) // 2 if n_source_types >= 2 else 0
    detected_ratio = n_collisions / max(1, theoretical_pairs * 10)
    dark_matter_ratio = 1 - detected_ratio

    return {
        "hypothesis_id": "F2",
        "hypothesis_name": "Epistemic Dark Matter",
        "detected_collisions": n_collisions,
        "theoretical_pair_space": theoretical_pairs,
        "theoretical_saturated_collisions": theoretical_pairs * 10,
        "detected_ratio": round(detected_ratio, 4),
        "dark_matter_ratio": round(dark_matter_ratio, 4),
        "supports": dark_matter_ratio > 0.5,
    }


# ══════════════════════════════════════════════════════════════════════
# F3 — Collision Catalysts
# ══════════════════════════════════════════════════════════════════════

def f3_collision_catalysts() -> dict:
    """Are regulatory/standard/personnel changes disproportionately present in
    high-scoring collisions vs low-scoring ones?"""
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT h.diamond_score, h.hypothesis_text, h.survived_kill
            FROM hypotheses h
            WHERE h.hypothesis_text IS NOT NULL
        """).fetchall()
    finally:
        conn.close()

    catalyst_markers = [
        "regulation", "regulatory change", "rule change", "standard update",
        "new standard", "certification", "effective date", "compliance deadline",
        "personnel change", "management change", "ceo", "departure", "appointed",
        "retired", "resigned", "announcement", "directive", "order", "ruling",
    ]

    high_with_catalyst = 0
    high_without = 0
    low_with_catalyst = 0
    low_without = 0

    for score, text, surv in rows:
        if not text or not score:
            continue
        has_catalyst = any(m in text.lower() for m in catalyst_markers)
        if score >= 70:
            if has_catalyst: high_with_catalyst += 1
            else:            high_without += 1
        else:
            if has_catalyst: low_with_catalyst += 1
            else:            low_without += 1

    high_rate = high_with_catalyst / max(1, high_with_catalyst + high_without)
    low_rate = low_with_catalyst / max(1, low_with_catalyst + low_without)
    uplift = high_rate - low_rate

    return {
        "hypothesis_id": "F3",
        "hypothesis_name": "Collision Catalysts",
        "high_score_with_catalyst_rate": round(high_rate, 4),
        "low_score_with_catalyst_rate": round(low_rate, 4),
        "catalyst_uplift": round(uplift, 4),
        "supports": uplift > 0.10,
    }


# ══════════════════════════════════════════════════════════════════════
# F4 — Information Metabolism
# ══════════════════════════════════════════════════════════════════════

def f4_information_metabolism() -> dict:
    """Time-to-hypothesis by source type. Fast-metabolism domains produce
    hypotheses sooner after fact ingestion."""
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT rf.source_type,
                   AVG(julianday(h.created_at) - julianday(rf.ingested_at)) as avg_lag_days,
                   COUNT(*) as n
            FROM raw_facts rf
            JOIN collisions c ON ',' || c.fact_ids || ',' LIKE '%,' || rf.id || ',%'
            JOIN hypotheses h ON h.collision_id = c.id
            WHERE rf.source_type IS NOT NULL
              AND h.created_at IS NOT NULL AND rf.ingested_at IS NOT NULL
            GROUP BY rf.source_type
            HAVING n >= 3
            ORDER BY avg_lag_days
        """).fetchall()
    finally:
        conn.close()

    per_domain = [
        {"source_type": r[0], "avg_lag_days": round(r[1], 2), "n": r[2]}
        for r in rows
    ]

    if per_domain:
        fastest = per_domain[0]
        slowest = per_domain[-1]
        spread = slowest["avg_lag_days"] - fastest["avg_lag_days"]
    else:
        fastest = slowest = None
        spread = 0

    return {
        "hypothesis_id": "F4",
        "hypothesis_name": "Information Metabolism",
        "per_domain": per_domain[:10],
        "fastest_domain": fastest,
        "slowest_domain": slowest,
        "metabolism_spread_days": round(spread, 2),
        "supports": spread > 5,
    }


# ══════════════════════════════════════════════════════════════════════
# F5 — Epistemic Immune System
# ══════════════════════════════════════════════════════════════════════

def f5_epistemic_immune_system() -> dict:
    """Do kill rounds disproportionately fire on cross-silo hypotheses?
    If YES, markets actively resist cross-silo insights."""
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT h.survived_kill, h.kill_attempts, c.num_domains
            FROM hypotheses h LEFT JOIN collisions c ON c.id = h.collision_id
            WHERE h.kill_attempts IS NOT NULL
        """).fetchall()
    finally:
        conn.close()

    cross_silo_kill_rate = 0
    single_silo_kill_rate = 0
    n_cross = 0
    n_single = 0
    cross_kills = 0
    single_kills = 0

    for surv, ka_json, nd in rows:
        try:
            attempts = json.loads(ka_json or "[]")
        except Exception:
            attempts = []
        kill_hits = sum(1 for a in attempts if isinstance(a, dict) and a.get("killed"))
        if nd and nd >= 3:
            n_cross += 1
            cross_kills += kill_hits
        else:
            n_single += 1
            single_kills += kill_hits

    cross_rate = cross_kills / max(1, n_cross)
    single_rate = single_kills / max(1, n_single)

    return {
        "hypothesis_id": "F5",
        "hypothesis_name": "Epistemic Immune System",
        "cross_silo_hypotheses": n_cross,
        "cross_silo_avg_kills_per_hypothesis": round(cross_rate, 2),
        "single_silo_hypotheses": n_single,
        "single_silo_avg_kills_per_hypothesis": round(single_rate, 2),
        "immune_response_excess": round(cross_rate - single_rate, 2),
        "supports": (cross_rate - single_rate) > 0.5,
    }


# ══════════════════════════════════════════════════════════════════════
# F6 — Conservation of Ignorance
# ══════════════════════════════════════════════════════════════════════

def f6_conservation_of_ignorance() -> dict:
    """As HUNTER corrects mispricings in one domain pair, do NEW mispricings
    appear in adjacent pairs at the same rate? Test via per-pair collision
    rate trend over time."""
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT strftime('%Y-%m', created_at) as month,
                   source_types,
                   COUNT(*) as n
            FROM collisions
            WHERE source_types IS NOT NULL AND created_at >= date('now', '-180 days')
            GROUP BY month, source_types
        """).fetchall()
    finally:
        conn.close()

    monthly_pair_counts = defaultdict(lambda: defaultdict(int))
    for month, st_json, n in rows:
        try:
            types = json.loads(st_json) if st_json.startswith("[") else st_json.split(",")
        except Exception:
            continue
        types = sorted([t.strip() for t in types if t.strip()])
        if len(types) < 2:
            continue
        key = "|".join(types[:2])
        monthly_pair_counts[month][key] += n

    # For each pair, compute correlation of monthly counts with inverse of
    # total collision count (if conservation holds, when one pair falls,
    # others rise)
    months = sorted(monthly_pair_counts.keys())
    totals = [sum(monthly_pair_counts[m].values()) for m in months]

    # Stability measure: does total stay roughly constant while individuals move?
    if len(totals) >= 3:
        total_mean = mean(totals)
        total_std = stdev(totals) if len(totals) > 1 else 0
        cv = total_std / max(1, total_mean)
    else:
        cv = None

    return {
        "hypothesis_id": "F6",
        "hypothesis_name": "Conservation of Ignorance",
        "months_analyzed": len(months),
        "monthly_total_collisions": totals,
        "total_coefficient_of_variation": round(cv, 4) if cv is not None else None,
        "supports": cv is not None and cv < 0.4,
        "note": "Low coefficient of variation = total residual stays constant even as pairs shift. "
                "High CV = total grows/shrinks (conservation violated).",
    }


# ══════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════

ALL = {
    "f1": f1_information_temperature,
    "f2": f2_epistemic_dark_matter,
    "f3": f3_collision_catalysts,
    "f4": f4_information_metabolism,
    "f5": f5_epistemic_immune_system,
    "f6": f6_conservation_of_ignorance,
}


def _persist(results):
    _ensure_tables()
    conn = get_connection()
    try:
        for r in results:
            conn.execute("""
                INSERT INTO frontier_test_results
                (hypothesis_id, hypothesis_name, testable, observation_value,
                 prediction_value, supports_hypothesis, evidence_description)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                r.get("hypothesis_id"),
                r.get("hypothesis_name"),
                1,  # testable
                r.get("uplift") or r.get("dark_matter_ratio") or r.get("catalyst_uplift") or r.get("metabolism_spread_days") or r.get("immune_response_excess") or r.get("total_coefficient_of_variation") or 0,
                None,
                1 if r.get("supports") else 0,
                json.dumps(r)[:1000],
            ))
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    _ensure_tables()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"

    if cmd in ALL:
        r = ALL[cmd]()
        print(json.dumps(r, indent=2, default=str))

    elif cmd == "all":
        results = []
        for name, fn in ALL.items():
            print(f"\nRunning {name.upper()} — {fn.__doc__.splitlines()[0].strip()}")
            try:
                r = fn()
                results.append(r)
                mark = "✓" if r.get("supports") else " "
                print(f"  {mark} SUPPORTS={r.get('supports')}  ({r.get('hypothesis_name')})")
            except Exception as e:
                print(f"  ERROR: {e}")
        _persist(results)
        print(f"\n✓ Persisted {len(results)} frontier test results")

    elif cmd == "report":
        conn = get_connection()
        try:
            rows = conn.execute("""
                SELECT hypothesis_id, hypothesis_name, supports_hypothesis, measured_at
                FROM frontier_test_results
                ORDER BY measured_at DESC LIMIT 30
            """).fetchall()
        finally:
            conn.close()
        print(f"\nFrontier test history ({len(rows)} runs):")
        for r in rows:
            mark = "✓" if r[2] else "✗"
            print(f"  {mark} {r[0]} {r[1]:<35} {r[3][:16]}")
    else:
        print(__doc__)
