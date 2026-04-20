"""Formula validator — answers the single most important open question:

  "Does compute_collision_formula() actually predict where collisions form?"

Method:
 1. Enumerate every unordered pair of source_types in DOMAIN_THEORY_PARAMS.
 2. For each pair, compute the theoretical score from compute_collision_formula().
 3. For each pair, count how many actual collisions in the data involve that pair.
 4. Correlate predicted score vs actual count (Pearson r, Spearman rho, p-value).
 5. Identify the 5 most over-predicted and most under-predicted pairs.
 6. Write a formula_validation row so the calibrator can act on it.

Decision rules:
  r >= 0.40, p < 0.05  → formula is predictive, keep weights
  0.20 <= r < 0.40     → partial signal, suggest coefficient adjustments
  r < 0.20             → formula weights are wrong or concept is mis-specified

Run:
    python formula_validator.py                # dry report
    python formula_validator.py write          # writes to formula_validation
"""

import json
import math
import sys
from datetime import datetime
from itertools import combinations
from statistics import mean, stdev

from database import get_connection
from theory import DOMAIN_THEORY_PARAMS, compute_collision_formula


def _pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return 0.0
    mx, my = mean(xs), mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if sx == 0 or sy == 0:
        return 0.0
    return num / (sx * sy)


def _spearman(xs, ys):
    def ranks(vals):
        indexed = sorted(range(len(vals)), key=lambda i: vals[i])
        r = [0] * len(vals)
        for rank, idx in enumerate(indexed, 1):
            r[idx] = rank
        return r
    return _pearson(ranks(xs), ranks(ys))


def _pvalue_from_r(r, n):
    """Two-sided approximate p-value using Fisher z-transform."""
    if abs(r) >= 0.9999 or n < 4:
        return 0.0 if abs(r) > 0.9 else 1.0
    z = 0.5 * math.log((1 + r) / (1 - r))
    se = 1 / math.sqrt(n - 3)
    z_score = z / se
    # Two-sided p from standard normal
    from math import erf
    p = 2 * (1 - 0.5 * (1 + erf(abs(z_score) / math.sqrt(2))))
    return max(0.0, min(1.0, p))


def _load_actual_pair_counts():
    """Count collisions by unordered source_type pair."""
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT source_types, domains_involved FROM collisions
        """).fetchall()
    finally:
        conn.close()

    pair_counts = {}
    for source_types, domains_involved in rows:
        types = []
        if source_types:
            try:
                types = json.loads(source_types) if source_types.startswith("[") else source_types.split(",")
            except Exception:
                types = source_types.split(",")
        if not types and domains_involved:
            try:
                types = json.loads(domains_involved)
            except Exception:
                pass
        types = [t.strip() for t in types if t and t.strip()]
        types = list({t for t in types if t in DOMAIN_THEORY_PARAMS})
        if len(types) < 2:
            continue
        for a, b in combinations(sorted(types), 2):
            pair_counts[(a, b)] = pair_counts.get((a, b), 0) + 1
    return pair_counts


def validate(write: bool = False) -> dict:
    actual = _load_actual_pair_counts()
    domains = sorted(DOMAIN_THEORY_PARAMS.keys())

    pairs = list(combinations(domains, 2))
    predicted = []
    observed = []
    detail = []
    for a, b in pairs:
        pred = compute_collision_formula(a, b)["total"]
        obs = actual.get((a, b), 0)
        predicted.append(pred)
        observed.append(obs)
        detail.append({"a": a, "b": b, "predicted": pred, "observed": obs})

    r = _pearson(predicted, observed)
    rho = _spearman(predicted, observed)
    p = _pvalue_from_r(r, len(predicted))

    # Residuals for calibration hints
    mean_obs = mean(observed) if observed else 0.0
    mean_pred = mean(predicted) if predicted else 0.0
    # Scale predicted to observed units before residual comparison
    if mean_pred > 0 and mean_obs > 0:
        scale = mean_obs / mean_pred
    else:
        scale = 1.0
    for d in detail:
        d["predicted_scaled"] = d["predicted"] * scale
        d["residual"] = d["observed"] - d["predicted_scaled"]

    over_predicted = sorted(detail, key=lambda d: d["residual"])[:5]
    under_predicted = sorted(detail, key=lambda d: -d["residual"])[:5]

    # Calibration-hint coefficient adjustments via simple linear regression
    # of observed ~ (silo_term, reinf_term, corr_term, resid_term).
    # Gives us component-level suggestions.
    import itertools
    X = []
    y = []
    for a, b in pairs:
        fa = compute_collision_formula(a, b)
        X.append([fa["silo_term"], fa["reinforcement_term"],
                  fa["correction_term"], fa["residual_term"]])
        y.append(actual.get((a, b), 0))
    # Solve normal equations A^T A x = A^T b
    try:
        import numpy as np
        Xa = np.array(X)
        ya = np.array(y)
        # Add constant term
        Xc = np.hstack([Xa, np.ones((len(Xa), 1))])
        betas, residuals, rank, sv = np.linalg.lstsq(Xc, ya, rcond=None)
        suggested = {
            "silo_coef_delta": float(betas[0]),
            "reinf_coef_delta": float(betas[1]),
            "corr_coef_delta": float(betas[2]),
            "resid_coef_delta": float(betas[3]),
            "intercept": float(betas[4]),
        }
    except Exception as e:
        suggested = {"error": str(e)}

    verdict = "weights_wrong"
    if abs(r) >= 0.40 and p < 0.05:
        verdict = "predictive"
    elif abs(r) >= 0.20:
        verdict = "partial_signal"

    summary = {
        "n_pairs": len(pairs),
        "n_observed_pairs": sum(1 for v in observed if v > 0),
        "pearson_r": round(r, 4),
        "spearman_rho": round(rho, 4),
        "p_value": round(p, 4),
        "verdict": verdict,
        "mean_observed": round(mean_obs, 2),
        "mean_predicted": round(mean_pred, 4),
        "over_predicted_top5": over_predicted,
        "under_predicted_top5": under_predicted,
        "suggested_coefficient_adjustments": suggested,
    }

    if not write:
        return summary

    conn = get_connection()
    try:
        # Add columns if missing (for tables created by calibration.py)
        existing = {r[1] for r in conn.execute("PRAGMA table_info(formula_validation)").fetchall()}
        extra = [
            ("n_pairs", "INTEGER"),
            ("n_observed_pairs", "INTEGER"),
            ("verdict", "TEXT"),
            ("detail_json", "TEXT"),
        ]
        for col, typ in extra:
            if col not in existing:
                try:
                    conn.execute(f"ALTER TABLE formula_validation ADD COLUMN {col} {typ}")
                except Exception:
                    pass
        conn.execute("""
            INSERT INTO formula_validation
            (date, pearson_r, spearman_rho, p_value, n_pairs, n_observed_pairs,
             formula_validated, suggested_silo_coeff, suggested_reinf_weight,
             suggested_corr_weight, suggested_resid_weight, verdict, detail_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.now().isoformat(),
            r, rho, p, len(pairs), summary["n_observed_pairs"],
            1 if verdict == "predictive" else 0,
            suggested.get("silo_coef_delta"), suggested.get("reinf_coef_delta"),
            suggested.get("corr_coef_delta"), suggested.get("resid_coef_delta"),
            verdict,
            json.dumps({"over": over_predicted, "under": under_predicted})[:5000],
        ))
        conn.commit()
        summary["persisted"] = True
    finally:
        conn.close()
    return summary


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "dry"
    s = validate(write=(cmd == "write"))
    print(f"\nFORMULA VALIDATION REPORT")
    print("=" * 60)
    print(f"Pairs tested:        {s['n_pairs']}")
    print(f"Pairs with data:     {s['n_observed_pairs']}")
    print(f"Pearson r:           {s['pearson_r']:+.4f}")
    print(f"Spearman rho:        {s['spearman_rho']:+.4f}")
    print(f"p-value:             {s['p_value']:.4f}")
    print(f"Verdict:             {s['verdict'].upper()}")
    print()
    print(f"Mean observed:       {s['mean_observed']} collisions/pair")
    print(f"Mean predicted:      {s['mean_predicted']} score/pair")
    print()
    print("MOST UNDER-PREDICTED (formula said less than reality shows):")
    for d in s["under_predicted_top5"]:
        print(f"  {d['a']:>20s} × {d['b']:<20s}  predicted={d['predicted']:.2f}  observed={d['observed']}")
    print()
    print("MOST OVER-PREDICTED (formula said more than reality shows):")
    for d in s["over_predicted_top5"]:
        print(f"  {d['a']:>20s} × {d['b']:<20s}  predicted={d['predicted']:.2f}  observed={d['observed']}")
    print()
    print("Suggested coefficient adjustments (regression deltas):")
    sa = s["suggested_coefficient_adjustments"]
    if "error" not in sa:
        print(f"  silo_coef:   {sa['silo_coef_delta']:+.4f}")
        print(f"  reinf_coef:  {sa['reinf_coef_delta']:+.4f}")
        print(f"  corr_coef:   {sa['corr_coef_delta']:+.4f}")
        print(f"  resid_coef:  {sa['resid_coef_delta']:+.4f}")
        print(f"  intercept:   {sa['intercept']:+.4f}")
