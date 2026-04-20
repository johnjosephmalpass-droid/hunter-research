"""Fit the empirical chain decay rate from the chains table.

Framework Layer 7 hardcoded CHAIN_DECAY_RATE = 0.273. This module fits
the actual decay from observed chain lengths. If the fit diverges
significantly from 0.273, the framework constant needs revision.

Method:
 1. Count chains at each depth d (1, 2, 3, ...).
 2. Fit log(count(d)) = log(count_0) - lambda * d via linear regression.
 3. Empirical decay rate = 1 - exp(-lambda) (per-depth multiplier).
 4. Compare to framework's 0.273 prediction.

Run:
    python chain_decay_fitter.py           # dry report
    python chain_decay_fitter.py write     # persist to theory_evidence
"""

import math
import sys
from collections import Counter
from datetime import datetime

from database import get_connection


FRAMEWORK_CHAIN_DECAY_RATE = 0.273


def fit(write: bool = False) -> dict:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT chain_length FROM chains WHERE chain_length IS NOT NULL AND chain_length >= 1"
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return {"n_chains": 0, "message": "No chains to fit."}

    depths = [int(r[0]) for r in rows]
    counts = Counter(depths)

    # Depths and log-counts for regression
    xs = sorted(counts.keys())
    if len(xs) < 2:
        return {
            "n_chains": len(depths),
            "message": f"Only {len(xs)} distinct depth(s) — need >=2 to fit decay.",
            "depth_counts": dict(counts),
        }

    log_ys = [math.log(counts[x]) for x in xs]

    # Least-squares fit: log(y) = a + b*x
    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(log_ys) / n
    ss_xy = sum((xs[i] - mean_x) * (log_ys[i] - mean_y) for i in range(n))
    ss_xx = sum((xs[i] - mean_x) ** 2 for i in range(n))
    if ss_xx == 0:
        return {
            "n_chains": len(depths),
            "message": "Degenerate regression.",
            "depth_counts": dict(counts),
        }
    b = ss_xy / ss_xx
    a = mean_y - b * mean_x

    # R² for goodness-of-fit
    predicted = [a + b * x for x in xs]
    ss_total = sum((y - mean_y) ** 2 for y in log_ys)
    ss_residual = sum((log_ys[i] - predicted[i]) ** 2 for i in range(n))
    r_squared = 1 - (ss_residual / ss_total) if ss_total > 0 else 0.0

    # lambda is the per-depth decay exponent. Slope b = -lambda.
    lam = -b
    decay_per_depth = 1 - math.exp(-lam) if lam > 0 else 0.0

    delta_from_framework = decay_per_depth - FRAMEWORK_CHAIN_DECAY_RATE

    verdict = "matches_framework"
    if abs(delta_from_framework) > 0.1 and r_squared > 0.3:
        verdict = "framework_constant_wrong" if r_squared > 0.5 else "uncertain_framework"

    summary = {
        "n_chains": len(depths),
        "depth_counts": dict(counts),
        "n_depths_observed": len(xs),
        "fitted_lambda": round(lam, 4),
        "fitted_decay_per_depth": round(decay_per_depth, 4),
        "r_squared": round(r_squared, 4),
        "framework_prediction": FRAMEWORK_CHAIN_DECAY_RATE,
        "delta_from_framework": round(delta_from_framework, 4),
        "verdict": verdict,
    }

    if write:
        conn = get_connection()
        try:
            conn.execute("""
                INSERT INTO theory_evidence
                (timestamp, source_event, source_id, layer, layer_name,
                 evidence_type, description, metric, observed_value,
                 predicted_value, unit, confidence, domain_pair,
                 chain_depth, cycle_detected, cycle_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                datetime.now().isoformat(),
                "chain_decay_fit", None,
                7, "L07_depth_value",
                "direct" if r_squared > 0.5 else "supporting",
                f"Fitted empirical chain decay rate = {decay_per_depth:.3f} "
                f"across {len(depths)} chains. R² = {r_squared:.3f}. "
                f"Framework predicted {FRAMEWORK_CHAIN_DECAY_RATE}. Verdict: {verdict}.",
                "chain_decay_per_depth",
                decay_per_depth,
                FRAMEWORK_CHAIN_DECAY_RATE,
                "fraction_per_depth",
                min(1.0, r_squared),
                "[]", 0, 0, None,
            ))
            conn.commit()
        finally:
            conn.close()
        summary["persisted"] = True

    return summary


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "dry"
    s = fit(write=(cmd == "write"))
    print("\nCHAIN DECAY FIT")
    print("=" * 60)
    if "message" in s:
        print(s["message"])
        print(f"Chains: {s.get('n_chains', 0)}")
        print(f"Depths: {s.get('depth_counts', {})}")
        sys.exit(0)

    print(f"Chains analysed:        {s['n_chains']}")
    print(f"Distinct depths:        {s['n_depths_observed']}")
    print(f"Depth counts:           {s['depth_counts']}")
    print()
    print(f"Fitted lambda:          {s['fitted_lambda']:+.4f}")
    print(f"Fitted decay per depth: {s['fitted_decay_per_depth']:.4f}")
    print(f"R² of fit:              {s['r_squared']:.4f}")
    print()
    print(f"Framework prediction:   {s['framework_prediction']}")
    print(f"Delta:                  {s['delta_from_framework']:+.4f}")
    print(f"Verdict:                {s['verdict'].upper()}")

    if "persisted" in s:
        print("\n✓ Written to theory_evidence")
