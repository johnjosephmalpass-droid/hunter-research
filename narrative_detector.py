"""Narrative structure detector.

Hypothesis: compelling narrative structure correlates with kill-survival
rate. Errors embedded in clean stories persist longer than errors
without narrative support.

Method (purely textual, no LLM calls required):
 1. Decompose each hypothesis into narrative components:
      - protagonist (asset/company/entity)
      - antagonist (a force, rule, or condition)
      - complication (what's broken / mispriced)
      - catalyst (the triggering event or date)
      - resolution (what corrects)
 2. Score narrative strength on five components (0..1 each).
 3. Correlate narrative strength with:
      - kill_survival (1/0)
      - diamond_score
      - portfolio P&L (if closed)

If narrative strength predicts survival or P&L, that's a new scoring
dimension worth formalising.

Run:
    python narrative_detector.py
    python narrative_detector.py write
"""

import json
import math
import re
import sys
from statistics import mean

from database import get_connection


# ── Lightweight linguistic markers ──

PROTAGONIST_PATTERNS = [
    r"\b[A-Z][A-Z0-9&]{1,5}\b",  # ticker-like
    r"\b(?:[A-Z][a-z]+\s+)+(?:Inc|Corp|Corporation|Ltd|LLC|REIT|Group|Holdings|Industries|Company)\b",
    r"\b(?:the\s+)?(?:pension|insurance|bank|hotel|office|industrial)\s+\w+\s+(?:sector|industry|market|companies|REITs?)\b",
]
ANTAGONIST_PATTERNS = [
    r"\b(?:regulator|regulation|rule|requirement|mandate|framework|model|formula|methodology|assumption)\b",
    r"\b(?:FERC|NAIC|SEC|FDA|EU|CMS|FASB|IASB|OSHA|EPA|CFTC|Federal Reserve)\b",
    r"\b(?:model|assumption)s?\s+(?:is|are|remain)\s+(?:wrong|outdated|stale|broken|invalid)\b",
]
COMPLICATION_PATTERNS = [
    r"\bmispric(?:e|ing|ed)\b",
    r"\bunderestimat(?:e|ing|ed)\b",
    r"\boverestimat(?:e|ing|ed)\b",
    r"\barbitrage\b",
    r"\b(?:systematically|materially|significantly)\s+(?:wrong|incorrect|miscalibrated)\b",
    r"\b(?:gap|mismatch|discrepancy|inconsistency|divergence)\b",
]
CATALYST_PATTERNS = [
    r"\b(?:20\d{2})\b",                          # explicit year
    r"\bQ[1-4]\s*20\d{2}\b",                     # quarter
    r"\b(?:March|April|May|June|July|August|September|October|November|December|January|February)\s+20\d{2}\b",
    r"\b(?:by|before|after|on|effective|within)\s+(?:\d+\s+(?:days?|weeks?|months?))\b",
    r"\b(?:maturity wall|catalyst|trigger|deadline|effective date)\b",
]
RESOLUTION_PATTERNS = [
    r"\b(?:repric(?:e|ing|ed)|correct(?:ion|ed|ing)?|revalu(?:e|ation|ed)|downgrad(?:e|ed)|writedown|impairment)\b",
    r"\b(?:settlement|adjustment|revision|amendment|rebase)\b",
    r"\b(?:converge|narrow|close|widen|compress|expand)\s+(?:spread|gap|differential)\b",
]


def _match_density(text: str, patterns: list, cap: int = 5) -> float:
    """Count unique matches across patterns, normalised to 0..1 by cap."""
    found = set()
    for rx in patterns:
        for m in re.findall(rx, text, flags=re.IGNORECASE):
            found.add(m.lower() if isinstance(m, str) else str(m))
    return min(1.0, len(found) / cap)


def score_narrative(hypothesis_text: str) -> dict:
    text = (hypothesis_text or "")[:5000]
    scores = {
        "protagonist": _match_density(text, PROTAGONIST_PATTERNS, 3),
        "antagonist": _match_density(text, ANTAGONIST_PATTERNS, 3),
        "complication": _match_density(text, COMPLICATION_PATTERNS, 3),
        "catalyst": _match_density(text, CATALYST_PATTERNS, 3),
        "resolution": _match_density(text, RESOLUTION_PATTERNS, 3),
    }
    scores["narrative_strength"] = round(mean(scores.values()), 4)
    scores["has_all_5_components"] = int(all(v > 0 for v in scores.values() if isinstance(v, (int, float))) and len(scores) >= 6)
    return scores


def _pearson(xs, ys):
    if len(xs) < 3:
        return 0.0
    mx, my = mean(xs), mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if sx == 0 or sy == 0:
        return 0.0
    return num / (sx * sy)


def analyse(write: bool = False) -> dict:
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT id, hypothesis_text, survived_kill, diamond_score
            FROM hypotheses
            WHERE hypothesis_text IS NOT NULL
        """).fetchall()
    finally:
        conn.close()

    if not rows:
        return {"n": 0, "message": "No hypotheses with text."}

    narrative_strengths = []
    survived = []
    scores = []
    per_hypothesis = []

    for hid, text, surv, ds in rows:
        ns = score_narrative(text or "")
        narrative_strengths.append(ns["narrative_strength"])
        survived.append(1 if surv else 0)
        scores.append(float(ds or 0))
        per_hypothesis.append({
            "id": hid,
            "narrative_strength": ns["narrative_strength"],
            "protagonist": ns["protagonist"],
            "antagonist": ns["antagonist"],
            "complication": ns["complication"],
            "catalyst": ns["catalyst"],
            "resolution": ns["resolution"],
            "survived_kill": surv,
            "diamond_score": ds,
        })

    r_ns_survival = _pearson(narrative_strengths, survived)
    r_ns_score = _pearson(narrative_strengths, scores)

    # Bucket analysis
    high_ns = [p for p in per_hypothesis if p["narrative_strength"] >= 0.6]
    low_ns = [p for p in per_hypothesis if p["narrative_strength"] < 0.4]
    high_survival = (
        sum(p["survived_kill"] or 0 for p in high_ns) / len(high_ns)
        if high_ns else 0.0
    )
    low_survival = (
        sum(p["survived_kill"] or 0 for p in low_ns) / len(low_ns)
        if low_ns else 0.0
    )

    summary = {
        "n_hypotheses": len(rows),
        "mean_narrative_strength": round(mean(narrative_strengths), 4) if narrative_strengths else 0,
        "r_narrative_vs_survival": round(r_ns_survival, 4),
        "r_narrative_vs_score": round(r_ns_score, 4),
        "high_narrative_count": len(high_ns),
        "high_narrative_survival_rate": round(high_survival, 4),
        "low_narrative_count": len(low_ns),
        "low_narrative_survival_rate": round(low_survival, 4),
        "survival_uplift_from_narrative": round(high_survival - low_survival, 4),
    }

    if write:
        conn = get_connection()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS narrative_scores (
                    hypothesis_id INTEGER PRIMARY KEY,
                    narrative_strength REAL,
                    protagonist REAL, antagonist REAL,
                    complication REAL, catalyst REAL, resolution REAL,
                    measured_at TEXT
                )
            """)
            from datetime import datetime
            now = datetime.now().isoformat()
            for p in per_hypothesis:
                conn.execute("""
                    INSERT OR REPLACE INTO narrative_scores
                    (hypothesis_id, narrative_strength, protagonist, antagonist,
                     complication, catalyst, resolution, measured_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (p["id"], p["narrative_strength"], p["protagonist"],
                      p["antagonist"], p["complication"], p["catalyst"],
                      p["resolution"], now))
            conn.commit()
        finally:
            conn.close()
    return summary


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "dry"
    s = analyse(write=(cmd == "write"))
    print(f"\nNARRATIVE STRUCTURE ANALYSIS")
    print("=" * 70)
    if "error" in s:
        print(f"Skipped: {s['error']}")
        sys.exit(0)
    print(f"Hypotheses analysed:              {s.get('n_hypotheses', 0)}")
    print(f"Mean narrative strength:          {s.get('mean_narrative_strength', 0):.3f}")
    print()
    print(f"Correlation (narrative → survival):  r = {s.get('r_narrative_vs_survival', 0):+.4f}")
    print(f"Correlation (narrative → score):     r = {s.get('r_narrative_vs_score', 0):+.4f}")
    print()
    print("Bucket analysis:")
    print(f"  High narrative (≥0.6):   n={s.get('high_narrative_count', 0)}, "
          f"survival={s.get('high_narrative_survival_rate', 0):.1%}")
    print(f"  Low narrative (<0.4):    n={s.get('low_narrative_count', 0)}, "
          f"survival={s.get('low_narrative_survival_rate', 0):.1%}")
    print(f"  Uplift from narrative:   {s.get('survival_uplift_from_narrative', 0):+.1%}")
    print()
    if abs(s.get("r_narrative_vs_survival", 0)) >= 0.3:
        print("→ STRONG signal. Add narrative_strength as a scoring dimension.")
    elif abs(s.get("r_narrative_vs_survival", 0)) >= 0.15:
        print("→ MODEST signal. Keep tracking; possibly useful with more data.")
    else:
        print("→ NO signal. Narrative structure not a predictor at current n.")
    if cmd == "write":
        print("\n✓ Written to narrative_scores table")
