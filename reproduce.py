#!/usr/bin/env python3
"""reproduce.py — regenerate every empirical claim in the preprint.

The pre-registered summer study requires that any number in the paper
can be regenerated from the current database + the current code. This
script does that regeneration and prints a manifest.

Usage:
    python reproduce.py              # regenerate and print
    python reproduce.py --json       # machine-readable JSON output
    python reproduce.py --claim X    # regenerate only claim X

Claims currently reproduced:
    C1 — collision formula r² vs actual pair counts
    C2 — 9 detected epistemic cycles (Tarjan SCC)
    C3 — per-domain half-life measurements
    C4 — 4-stratum alpha distribution (requires closed positions)
    C5 — kill-failure topology (structural incompleteness candidates)
    C6 — 2-of-9 cycle types empirically distinguished

Each claim cites the analyser module that generated it and the DB table
where the numbers live. Reviewers can audit any number by running the
named module themselves.
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).parent


def _import_or_skip(module_name):
    try:
        return __import__(module_name)
    except Exception as e:
        print(f"[!] {module_name} unavailable: {e}")
        return None


def c1_formula():
    """Claim 1: Does the collision formula predict pair-level collision density?"""
    fv = _import_or_skip("formula_validator")
    if not fv:
        return {"claim": "C1", "status": "module_unavailable"}
    r = fv.validate(write=False)
    return {
        "claim": "C1",
        "question": "Does compute_collision_formula predict actual pair-level collision density?",
        "method": "Pearson r on 153 pairs, predicted score vs observed collision count.",
        "module": "formula_validator.py",
        "table": "formula_validation",
        "pearson_r": r["pearson_r"],
        "p_value": r["p_value"],
        "verdict": r["verdict"],
    }


def c2_cycles():
    """Claim 2: Epistemic cycles exist and are detectable."""
    cd = _import_or_skip("cycle_detector")
    if not cd:
        return {"claim": "C2", "status": "module_unavailable"}
    r = cd.detect_cycles(dry_run=True)
    return {
        "claim": "C2",
        "question": "Do closed-loop epistemic cycles exist in the corpus?",
        "method": "Tarjan SCC over causal graph with 0.78 semantic node merging.",
        "module": "cycle_detector.py",
        "table": "detected_cycles",
        "edges_processed": r.get("edges"),
        "nodes": r.get("nodes"),
        "cycles_detected": r.get("cycles"),
    }


def c3_halflife():
    """Claim 3: Compositional residuals persist longer than framework predicted."""
    hl = _import_or_skip("halflife_estimator")
    if not hl:
        return {"claim": "C3", "status": "module_unavailable"}
    r = hl.estimate(write=False)
    return {
        "claim": "C3",
        "question": "What is the empirical half-life of compositional residuals?",
        "method": "MLE with right-censoring on corrected-vs-uncorrected observations.",
        "module": "halflife_estimator.py",
        "table": "halflife_estimates",
        "global_halflife_days": r["global"].get("half_life_days"),
        "framework_prediction_days": 120,
        "delta_days": r["global"].get("delta_vs_prediction_days"),
    }


def c4_strata():
    """Claim 4: Alpha increases monotonically with domain count."""
    try:
        import sqlite3
        conn = sqlite3.connect(HERE / "hunter.db")
        # Count collisions per stratum (not alpha yet — no closed positions)
        by_stratum = {"A": 0, "B": 0, "C": 0, "D": 0}
        rows = conn.execute("SELECT num_domains FROM collisions").fetchall()
        for r in rows:
            nd = r[0] or 0
            if nd == 1: by_stratum["A"] += 1
            elif nd == 2: by_stratum["B"] += 1
            elif nd == 3: by_stratum["C"] += 1
            elif nd >= 4: by_stratum["D"] += 1
        conn.close()
        return {
            "claim": "C4",
            "question": "Does portfolio alpha increase monotonically A < B < C < D?",
            "method": "4-stratum pre-registered paired bootstrap (summer 2026 will populate).",
            "module": "preregister.py + portfolio.py",
            "table": "preregistration.json + portfolio_positions",
            "current_strata_counts": by_stratum,
            "status": "awaiting_closed_positions_summer_2026",
        }
    except Exception as e:
        return {"claim": "C4", "status": f"error: {e}"}


def c5_kill_topology():
    """Claim 5: Structural incompleteness is mappable."""
    kf = _import_or_skip("kill_failure_mapper")
    if not kf:
        return {"claim": "C5", "status": "module_unavailable"}
    r = kf.map_failures(write=False)
    return {
        "claim": "C5",
        "question": "Where do adversarial kill rounds systematically fail?",
        "method": "Aggregate kill_type × outcome across all surviving hypotheses.",
        "module": "kill_failure_mapper.py",
        "table": "kill_failure_topology",
        "pairs_analysed": r["n_pairs_analysed"],
        "top_structural_pairs": [
            {"pair": p["pair"], "failure_rate": p["failure_rate"],
             "survival_rate": p["survival_rate"]}
            for p in r["top_structural_pairs"][:5]
        ],
    }


def c6_cycle_taxonomy():
    """Claim 6: The 9-cycle taxonomy has empirical support."""
    try:
        import sqlite3
        conn = sqlite3.connect(HERE / "hunter.db")
        rows = conn.execute("""
            SELECT cycle_type, COUNT(*) as n
            FROM detected_cycles GROUP BY cycle_type
        """).fetchall()
        conn.close()
        types_detected = {r[0]: r[1] for r in rows}
        return {
            "claim": "C6",
            "question": "How many of the 9 cycle types are empirically distinguishable?",
            "method": "Cycle detector classifies each detected cycle by type.",
            "module": "cycle_detector.py",
            "table": "detected_cycles",
            "types_detected": types_detected,
            "distinct_types_found": len(types_detected),
        }
    except Exception as e:
        return {"claim": "C6", "status": f"error: {e}"}


CLAIMS = {
    "C1": c1_formula,
    "C2": c2_cycles,
    "C3": c3_halflife,
    "C4": c4_strata,
    "C5": c5_kill_topology,
    "C6": c6_cycle_taxonomy,
}


def main():
    ap = argparse.ArgumentParser(description="Regenerate preprint claims from live data.")
    ap.add_argument("--claim", help="Specific claim (C1-C6); default: all")
    ap.add_argument("--json", action="store_true", help="JSON output")
    args = ap.parse_args()

    to_run = [args.claim] if args.claim else list(CLAIMS.keys())
    results = {
        "generated_at": datetime.now().isoformat(),
        "claims": {},
    }
    for c in to_run:
        if c in CLAIMS:
            print(f"Reproducing {c}...", file=sys.stderr)
            try:
                results["claims"][c] = CLAIMS[c]()
            except Exception as e:
                results["claims"][c] = {"claim": c, "error": str(e)}

    if args.json:
        print(json.dumps(results, indent=2, default=str))
    else:
        print("\n" + "=" * 70)
        print(f"  REPRODUCTION MANIFEST  {results['generated_at']}")
        print("=" * 70)
        for cid, data in results["claims"].items():
            print(f"\n  {cid}: {data.get('question', '')}")
            for k, v in data.items():
                if k == "question": continue
                if isinstance(v, (dict, list)):
                    print(f"      {k}: {json.dumps(v, default=str)[:200]}")
                else:
                    print(f"      {k}: {v}")

if __name__ == "__main__":
    main()
