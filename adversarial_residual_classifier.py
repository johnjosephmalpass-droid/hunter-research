"""Classify each surviving hypothesis's residual as accidental vs adversarial.

Framework assumes all residual arises from translation loss, silo separation,
correction lag. But some errors are deliberately maintained — regulatory
capture, strategic ambiguity, disinformation campaigns. These have
different persistence dynamics and require different correction paths.

Taxonomy:
  accidental     — translation loss, no active maintainer
  self_reinforcing — narrative-driven echo chamber (no deliberate actor)
  adversarial    — specific actor benefits from the error persisting
  regulatory     — captured regulator protects the error
  structural     — mathematically unreachable by market correction

Uses lightweight text pattern matching + domain heuristics. An LLM-refined
version could replace this — deliberately keeping it cheap so it runs on
every hypothesis for free.

Run:
    python adversarial_residual_classifier.py
    python adversarial_residual_classifier.py write
"""

import re
import sys
from collections import Counter, defaultdict
from datetime import datetime

from database import get_connection


MAINTAINER_PATTERNS = {
    "regulatory": [
        r"\b(?:regulator|regulatory|oversight|agency)\s+(?:failed|ignored|allowed|permitted|sanctioned)\b",
        r"\b(?:captured|capture|influenced|lobbied)\s+(?:regulator|agency)\b",
        r"\b(?:regulatory capture|regulatory forbearance|regulatory arbitrage)\b",
        r"\b(?:FERC|SEC|CFTC|FDA|EPA|OSHA|CFPB|NAIC)\s+(?:has not|have not|fails to|refuses to|ignores)\b",
    ],
    "strategic": [
        r"\b(?:opacity|opaqueness|non-disclosure|confidential)\b.{0,50}\b(?:benefits|advantages|helps)\b",
        r"\b(?:rating agency|rater|issuer)\s+(?:incentive|conflict|preserves|maintains)\b",
        r"\b(?:strategic ambiguity|deliberate vagueness|purposefully unclear)\b",
        r"\b(?:incumbent|moat|barrier)\s+(?:protected|maintained)\s+by\b",
    ],
    "disinformation": [
        r"\b(?:disinformation|misinformation|propaganda|manipulated)\b",
        r"\b(?:pump|spoof|wash trade|painting the tape)\b",
    ],
}

STRUCTURAL_PATTERNS = [
    r"\b(?:no (?:single|one)\s+(?:analyst|practitioner|specialist)\s+(?:reads|sees|monitors))\b",
    r"\b(?:cross-silo|cross-domain|cross-sectoral)\s+(?:blindspot|blind spot|gap)\b",
    r"\b(?:translation loss|information loss|compressed)\b",
    r"\b(?:no natural|no existing|no market)\s+(?:instrument|correction|arbitrageur)\b",
]

ACCIDENTAL_PATTERNS = [
    r"\b(?:stale|outdated|obsolete|legacy)\s+(?:model|assumption|framework|formula)\b",
    r"\b(?:lag|delay|slow to update|not yet reflect(?:ed)?)\b",
    r"\b(?:calibrat(?:ion|ed) (?:before|prior to|based on)\s+\d{4})\b",
]

SELF_REINFORCING_PATTERNS = [
    r"\b(?:consensus|widely accepted|standard assumption|everyone assumes)\b",
    r"\b(?:conventional wisdom|received wisdom|industry narrative)\b",
    r"\b(?:repeat(?:ed|edly)\s+by|cited in|circulated)\b.{0,60}\b(?:analyst|research|report|trade press)\b",
]


def classify(text: str) -> dict:
    text_lower = (text or "")[:5000]

    scores = {}
    for name, patterns in MAINTAINER_PATTERNS.items():
        s = sum(1 for rx in patterns if re.search(rx, text_lower, re.IGNORECASE))
        scores[name] = s

    struct = sum(1 for rx in STRUCTURAL_PATTERNS if re.search(rx, text_lower, re.IGNORECASE))
    accid = sum(1 for rx in ACCIDENTAL_PATTERNS if re.search(rx, text_lower, re.IGNORECASE))
    self_r = sum(1 for rx in SELF_REINFORCING_PATTERNS if re.search(rx, text_lower, re.IGNORECASE))

    # Pick highest-scoring classification (break ties toward accidental)
    totals = {
        "regulatory": scores["regulatory"],
        "adversarial_strategic": scores["strategic"],
        "adversarial_disinformation": scores["disinformation"],
        "structural": struct,
        "self_reinforcing": self_r,
        "accidental": accid,
    }
    category = max(totals, key=lambda k: (totals[k], {
        "accidental": 0, "self_reinforcing": 1, "structural": 2,
        "regulatory": 3, "adversarial_strategic": 4, "adversarial_disinformation": 5,
    }[k]))
    if totals[category] == 0:
        category = "unknown"

    # Adversarial umbrella flag
    adversarial = category in ("regulatory", "adversarial_strategic",
                                "adversarial_disinformation")

    return {
        "category": category,
        "is_adversarial": adversarial,
        "marker_counts": totals,
        "confidence": min(1.0, totals.get(category, 0) / 3.0) if totals.get(category) else 0.0,
    }


def classify_all(write: bool = False) -> dict:
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT id, hypothesis_text, survived_kill, diamond_score
            FROM hypotheses
            WHERE hypothesis_text IS NOT NULL
        """).fetchall()
    finally:
        conn.close()

    results = []
    cat_counter = Counter()
    by_survival = {"survived": Counter(), "killed": Counter()}
    score_by_cat = defaultdict(list)

    for hid, text, surv, ds in rows:
        r = classify(text or "")
        r["hypothesis_id"] = hid
        r["survived_kill"] = bool(surv)
        r["diamond_score"] = ds
        results.append(r)
        cat_counter[r["category"]] += 1
        bucket = "survived" if surv else "killed"
        by_survival[bucket][r["category"]] += 1
        if ds:
            score_by_cat[r["category"]].append(ds)

    # Average score by category
    avg_by_cat = {
        c: round(sum(s) / len(s), 2) for c, s in score_by_cat.items() if s
    }

    summary = {
        "n_hypotheses": len(rows),
        "by_category": dict(cat_counter),
        "by_survival": {k: dict(v) for k, v in by_survival.items()},
        "avg_score_by_category": avg_by_cat,
        "adversarial_count": sum(
            1 for r in results if r["is_adversarial"]
        ),
        "adversarial_pct": round(
            sum(1 for r in results if r["is_adversarial"]) / max(1, len(results)) * 100, 1
        ),
    }

    if write:
        conn = get_connection()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS residual_classifications (
                    hypothesis_id INTEGER PRIMARY KEY,
                    category TEXT, is_adversarial INTEGER,
                    confidence REAL, marker_counts_json TEXT,
                    measured_at TEXT
                )
            """)
            import json as _json
            now = datetime.now().isoformat()
            for r in results:
                conn.execute("""
                    INSERT OR REPLACE INTO residual_classifications
                    (hypothesis_id, category, is_adversarial, confidence,
                     marker_counts_json, measured_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (r["hypothesis_id"], r["category"],
                      1 if r["is_adversarial"] else 0,
                      r["confidence"],
                      _json.dumps(r["marker_counts"]),
                      now))
            conn.commit()
        finally:
            conn.close()

    return summary


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "dry"
    s = classify_all(write=(cmd == "write"))
    print(f"\nADVERSARIAL vs ACCIDENTAL RESIDUAL CLASSIFICATION")
    print("=" * 70)
    print(f"Hypotheses classified: {s['n_hypotheses']}")
    print(f"Adversarial: {s['adversarial_count']} ({s['adversarial_pct']}%)")
    print()
    print("By category:")
    for cat, n in sorted(s["by_category"].items(), key=lambda x: -x[1]):
        avg = s["avg_score_by_category"].get(cat, 0)
        surv_n = s["by_survival"]["survived"].get(cat, 0)
        killed_n = s["by_survival"]["killed"].get(cat, 0)
        survival_rate = surv_n / max(1, surv_n + killed_n)
        print(f"  {cat:<30} n={n:>3}   surv={surv_n:>2} killed={killed_n:>2} "
              f"surv_rate={survival_rate:.0%}  avg_score={avg}")
    print()
    print("Interpretation:")
    print("  Adversarial / regulatory residual should persist longer in tests —")
    print("  there's an active maintainer resisting correction. Structural")
    print("  residual should persist longest of all (mathematically unreachable).")
    if cmd == "write":
        print("\n✓ Written to residual_classifications table")
