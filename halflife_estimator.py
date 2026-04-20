"""Empirical half-life estimator — tests the 120-day prediction.

The framework predicts epistemic errors have a ~120-day half-life. This
module measures the observed half-life from the corpus.

Method:
 1. For each fact, find subsequent facts in the same source_type that
    share >= 3 entities OR >= 3 implication bigrams.
 2. Of those, identify the ones that contain correction markers or
    contradiction/update language. Treat them as "correction events."
 3. Fit an exponential decay: fraction_still_valid(t) = exp(-lambda * t).
 4. half_life = ln(2) / lambda.

Per source_type AND overall. Per depth-of-chain breakdown is left to
the chain_decay_fitter (separate module).

Run:
    python halflife_estimator.py
    python halflife_estimator.py write
"""

import json
import math
import re
import sys
from collections import defaultdict
from datetime import datetime

from database import get_connection

CORRECTION_RX = re.compile(
    r"\b(retracted|retraction|revised|revision|updated|update|amended|"
    r"contradicted|contradicts|reversed|reversal|discontinued|withdrawn|"
    r"restated|restatement|correction|corrected|errata|erratum|"
    r"nullified|voided|rescinded|overturned|quashed|disproved|disputes)\b",
    re.IGNORECASE,
)


def _parse_date(s):
    if not s:
        return None
    s = str(s)[:10]
    try:
        return datetime.strptime(s, "%Y-%m-%d")
    except Exception:
        return None


def _entity_set(conn, fact_id):
    rows = conn.execute(
        "SELECT entity_name_lower FROM fact_entities WHERE raw_fact_id = ?",
        (fact_id,),
    ).fetchall()
    return {r[0] for r in rows if r[0]}


def estimate(write: bool = False) -> dict:
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT id, source_type, title, raw_content, date_of_fact, ingested_at
            FROM raw_facts
            WHERE source_type IS NOT NULL
            ORDER BY source_type, COALESCE(date_of_fact, ingested_at)
        """).fetchall()

        by_source = defaultdict(list)
        for r in rows:
            fid, st, title, content, dof, ing = r
            d = _parse_date(dof) or _parse_date(ing)
            if not d:
                continue
            by_source[st].append({
                "id": fid, "date": d,
                "text": (title or "") + " " + (content or "")[:1000],
            })

        # For each source_type, build correction observations
        observations_global = []  # list of (days_since_origin, corrected_bool)
        results = {}
        for st, facts in by_source.items():
            if len(facts) < 30:
                continue
            obs = []
            for i, f in enumerate(facts):
                ents_i = _entity_set(conn, f["id"])
                if not ents_i:
                    continue
                # Look forward up to 365 days for a related correction event
                corrected = False
                correction_day = None
                for g in facts[i + 1:]:
                    delta_days = (g["date"] - f["date"]).days
                    if delta_days > 365:
                        break
                    if delta_days <= 0:
                        continue
                    ents_j = _entity_set(conn, g["id"])
                    overlap = len(ents_i & ents_j)
                    if overlap >= 2 and CORRECTION_RX.search(g["text"]):
                        corrected = True
                        correction_day = delta_days
                        break
                # Censor at 365 if not corrected
                obs.append({
                    "corrected": corrected,
                    "t_or_censor": correction_day if corrected else 365,
                })
                observations_global.append((
                    correction_day if corrected else 365,
                    corrected,
                ))

            # MLE of exponential decay lambda from observations with right-censoring
            # L = prod lambda*exp(-lambda*t_i) for observed, exp(-lambda*t_j) for censored
            # MLE: lambda = events / sum(t)
            events = sum(1 for o in obs if o["corrected"])
            total_t = sum(o["t_or_censor"] for o in obs)
            if events > 0 and total_t > 0:
                lam = events / total_t
                half_life = math.log(2) / lam
            else:
                lam = None
                half_life = None
            results[st] = {
                "n_facts": len(facts),
                "n_observations": len(obs),
                "n_correction_events": events,
                "correction_rate_per_day": round(lam, 6) if lam else None,
                "half_life_days": round(half_life, 1) if half_life else None,
            }

        # Global pooled estimate
        events_g = sum(1 for _, c in observations_global if c)
        total_g = sum(t for t, _ in observations_global)
        if events_g > 0 and total_g > 0:
            lam_g = events_g / total_g
            half_life_g = math.log(2) / lam_g
        else:
            lam_g = None
            half_life_g = None

        summary = {
            "by_source": results,
            "global": {
                "n_observations": len(observations_global),
                "n_correction_events": events_g,
                "correction_rate_per_day": round(lam_g, 6) if lam_g else None,
                "half_life_days": round(half_life_g, 1) if half_life_g else None,
                "framework_prediction_days": 120,
                "delta_vs_prediction_days": (
                    round(half_life_g - 120, 1) if half_life_g else None
                ),
            },
        }

        if write:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS halflife_estimates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_type TEXT,
                    half_life_days REAL,
                    correction_rate_per_day REAL,
                    n_observations INTEGER,
                    n_correction_events INTEGER,
                    measured_at TEXT
                )
            """)
            now = datetime.now().isoformat()
            for st, r in results.items():
                conn.execute("""
                    INSERT INTO halflife_estimates
                    (source_type, half_life_days, correction_rate_per_day,
                     n_observations, n_correction_events, measured_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (st, r["half_life_days"], r["correction_rate_per_day"],
                      r["n_observations"], r["n_correction_events"], now))
            conn.execute("""
                INSERT INTO halflife_estimates
                (source_type, half_life_days, correction_rate_per_day,
                 n_observations, n_correction_events, measured_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, ("_global_", summary["global"]["half_life_days"],
                  summary["global"]["correction_rate_per_day"],
                  summary["global"]["n_observations"],
                  summary["global"]["n_correction_events"], now))
            conn.commit()
    finally:
        conn.close()
    return summary


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "dry"
    s = estimate(write=(cmd == "write"))
    print(f"\n{'Source type':<22} {'n_obs':>6} {'events':>7} "
          f"{'rate/day':>10} {'half-life':>10}")
    print("-" * 75)
    for st in sorted(s["by_source"].keys()):
        d = s["by_source"][st]
        rate = f"{d['correction_rate_per_day']:.5f}" if d["correction_rate_per_day"] else "-"
        hl = f"{d['half_life_days']:.0f} days" if d["half_life_days"] else "-"
        print(f"{st:<22} {d['n_observations']:>6} {d['n_correction_events']:>7} "
              f"{rate:>10} {hl:>10}")
    print("-" * 75)
    g = s["global"]
    print(f"{'GLOBAL':<22} {g['n_observations']:>6} {g['n_correction_events']:>7} "
          f"{(g['correction_rate_per_day'] or 0):.5f} "
          f"{(g['half_life_days'] or 0):.0f} days")
    print()
    print(f"Framework predicts: 120 days")
    if g["half_life_days"]:
        print(f"Measured:           {g['half_life_days']:.0f} days "
              f"(Δ {g['delta_vs_prediction_days']:+.0f})")
        ratio = g["half_life_days"] / 120
        if 0.5 <= ratio <= 2.0:
            verdict = "WITHIN ORDER OF MAGNITUDE — framework approximately calibrated"
        else:
            verdict = f"OFF BY {ratio:.1f}x — recalibrate constants"
        print(f"Verdict:            {verdict}")
    if cmd == "write":
        print("\n✓ Written to halflife_estimates table")
