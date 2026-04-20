"""Pre-registration for the Summer 2026 empirical study.

Without pre-registration the study isn't credible. You can always find a
cut of the data where X beats Y if you look hard enough. Pre-registration
forces you to declare the hypotheses, strata, corpus cutoff, and primary
endpoint BEFORE looking at the outcomes.

This module:
 1. Freezes the fact corpus at a cutoff date (default: 2024-12-31).
 2. Records the set of fact IDs that are in-corpus.
 3. Defines the 4 strata (A/B/C/D) by number of distinct domains in each
    collision/hypothesis.
 4. Declares the primary endpoint (alpha monotonically increases from A to D).
 5. Declares the null baselines that MUST be run (random-pair control,
    within-silo control, shuffle-label control).
 6. Writes a `preregistration.json` manifest signed with the current
    git/code hash so nothing can be silently changed later.

Once written, attempting to modify the manifest produces a warning.
The summer analysis script must load this manifest and fail-loud if
the corpus or strata drift.

Run:
    python preregister.py write         # creates manifest
    python preregister.py verify        # checks manifest matches code/data
    python preregister.py status        # prints strata sizes + power analysis
"""

import hashlib
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from database import get_connection

MANIFEST_PATH = Path(__file__).parent / "preregistration.json"
CORPUS_CUTOFF = "2024-12-31"  # Default: facts on/before this date are in-corpus
HOLDOUT_START = "2025-01-01"  # Market-price data from this date forward validates hypotheses


def _fact_ids_on_or_before(cutoff: str) -> list:
    """Return sorted fact IDs whose date_of_fact <= cutoff (or ingested_at if missing)."""
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT id FROM raw_facts
            WHERE (date_of_fact IS NOT NULL AND date_of_fact <= ?)
               OR (date_of_fact IS NULL AND date(ingested_at) <= ?)
            ORDER BY id
        """, (cutoff, cutoff)).fetchall()
        return [r[0] for r in rows]
    finally:
        conn.close()


def _count_by_stratum(fact_ids: list) -> dict:
    """Count how many collisions (in current data) fall into each stratum
    by their `num_domains` count. Useful for power analysis preview."""
    if not fact_ids:
        return {"A": 0, "B": 0, "C": 0, "D": 0}
    fid_set = set(fact_ids)
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT id, num_domains, fact_ids FROM collisions
        """).fetchall()
    finally:
        conn.close()

    strata = {"A": 0, "B": 0, "C": 0, "D": 0}
    strata_partial = {"A": 0, "B": 0, "C": 0, "D": 0}
    for cid, nd, fids_json in rows:
        try:
            cf = json.loads(fids_json or "[]")
        except Exception:
            continue
        if nd is None or not cf:
            continue
        in_corpus = sum(1 for f in cf if f in fid_set)
        pct = in_corpus / len(cf)
        # Strict: all facts in-corpus
        strict = pct == 1.0
        # Partial: majority of facts in-corpus (for preview only)
        partial = pct >= 0.5
        bucket = None
        if nd == 1:
            bucket = "A"
        elif nd == 2:
            bucket = "B"
        elif nd == 3:
            bucket = "C"
        elif nd >= 4:
            bucket = "D"
        if not bucket:
            continue
        if strict:
            strata[bucket] += 1
        if partial:
            strata_partial[bucket] += 1
    # Attach partial preview via side attribute
    strata["_partial"] = strata_partial
    return strata


def _code_hash() -> str:
    """Hash the core engine files so we can detect scoring changes mid-study."""
    files = [
        "hunter.py", "prompts.py", "config.py", "theory.py",
        "thesis_dedup.py", "portfolio_feedback.py", "cycle_detector.py",
    ]
    h = hashlib.sha256()
    here = Path(__file__).parent
    for fn in files:
        p = here / fn
        if p.exists():
            h.update(fn.encode())
            h.update(b"\0")
            h.update(p.read_bytes())
            h.update(b"\0")
    return h.hexdigest()[:16]


def _build_manifest(cutoff: str = CORPUS_CUTOFF, holdout_start: str = HOLDOUT_START) -> dict:
    fact_ids = _fact_ids_on_or_before(cutoff)
    strata_full = _count_by_stratum(fact_ids)
    strata_partial = strata_full.pop("_partial", {"A": 0, "B": 0, "C": 0, "D": 0})
    strata = strata_full
    total_collisions_in_scope = sum(strata.values())

    # Power analysis: McNemar-style paired test needs ~30+ per stratum
    # for a reasonable effect size. Flag if we're short.
    sufficient = all(v >= 30 for v in strata.values())

    return {
        "created_at": datetime.now().isoformat(),
        "study_name": "HUNTER Compositional Alpha Study, Summer 2026",
        "study_duration_weeks": 12,
        "corpus_cutoff": cutoff,
        "holdout_start": holdout_start,
        "corpus_fact_count": len(fact_ids),
        "corpus_fact_id_hash": hashlib.sha256(json.dumps(fact_ids).encode()).hexdigest()[:32],
        "corpus_fact_id_sample": fact_ids[:20] + fact_ids[-20:] if len(fact_ids) > 40 else fact_ids,
        "code_hash": _code_hash(),
        "strata": {
            "A": {
                "name": "Single-domain control",
                "criterion": "num_domains == 1",
                "expected_alpha_sign": "≈ 0 (null)",
                "n_in_corpus": strata["A"],
            },
            "B": {
                "name": "Two-domain baseline",
                "criterion": "num_domains == 2",
                "expected_alpha_sign": "small positive",
                "n_in_corpus": strata["B"],
            },
            "C": {
                "name": "Three-domain",
                "criterion": "num_domains == 3",
                "expected_alpha_sign": "positive",
                "n_in_corpus": strata["C"],
            },
            "D": {
                "name": "Four-plus-domain (compositional)",
                "criterion": "num_domains >= 4",
                "expected_alpha_sign": "large positive",
                "n_in_corpus": strata["D"],
            },
        },
        "primary_hypothesis": (
            "Median portfolio alpha (vs SPY total return over "
            "position time_window_days) increases monotonically: "
            "A ≤ B ≤ C ≤ D, with D−A > 0 at p < 0.05 via paired "
            "bootstrap (10,000 resamples)."
        ),
        "secondary_hypotheses": [
            "H2: Detected cycles (detected_cycles table, reinforcement >= 0.5) "
            "persist (remain un-corrected in the market) for >= 14 days in "
            "≥ 2 of 9 known cycles.",
            "H3: Cross-silo collisions (domain_distance >= 0.60) produce "
            "higher adjusted_score than within-silo (< 0.30) by >= 10 points "
            "on average.",
            "H4: Chain depth d=3 hypotheses outperform d=1 hypotheses in "
            "realised alpha with effect size Cohen's d >= 0.3.",
        ],
        "null_baselines": [
            {
                "name": "random_pair_control",
                "method": "Randomly pair N facts from distinct source types. "
                          "Run the full pipeline. Compare alpha to strata B.",
                "expected_result": "random_pair alpha ≤ stratum_B alpha",
            },
            {
                "name": "within_silo_control",
                "method": "Run pipeline forcing both facts to share source_type. "
                          "Compare alpha to strata A.",
                "expected_result": "within_silo alpha ≈ stratum_A alpha",
            },
            {
                "name": "shuffle_label_control",
                "method": "Shuffle the source_type labels on facts before running. "
                          "Compare alpha.",
                "expected_result": "shuffled alpha ≈ 0 (destroys cross-silo signal)",
            },
        ],
        "decision_rules": {
            "primary_wins": "D − A > 0, p < 0.05, monotonicity holds. "
                           "Accept compositional alpha hypothesis.",
            "primary_loses": "D ≤ B OR monotonicity violated. "
                            "Reject. Write null-result paper.",
            "must_not_do": [
                "Do not add new facts to the corpus after the cutoff.",
                "Do not change scoring weights after the cutoff.",
                "Do not swap primary endpoint for secondary if primary fails.",
                "Do not exclude hypotheses retroactively for 'quality'.",
                "Report ALL 4 strata outcomes even if one is embarrassing.",
            ],
        },
        "power_analysis": {
            "min_n_per_stratum_recommended": 30,
            "current_sufficient": sufficient,
            "total_collisions_in_scope": total_collisions_in_scope,
            "notes": "Power analysis assumes Cohen's d = 0.3, alpha = 0.05, "
                     "power = 0.80. If a stratum < 30, need to run more cycles.",
        },
        "strata_partial": strata_partial,
    }


def write_manifest(cutoff: str = CORPUS_CUTOFF) -> dict:
    if MANIFEST_PATH.exists():
        print(f"WARNING: {MANIFEST_PATH} already exists. This will OVERWRITE it.")
        print("That voids pre-registration. If you're sure, delete the file first.")
        return {}
    manifest = _build_manifest(cutoff=cutoff)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2))
    return manifest


def verify_manifest() -> dict:
    """Compare current state to the written manifest. Flag any drift."""
    if not MANIFEST_PATH.exists():
        return {"status": "no_manifest", "message": "No preregistration.json found."}
    manifest = json.loads(MANIFEST_PATH.read_text())

    current_fact_ids = _fact_ids_on_or_before(manifest["corpus_cutoff"])
    current_hash = hashlib.sha256(json.dumps(current_fact_ids).encode()).hexdigest()[:32]
    current_code = _code_hash()

    drift = []
    if current_hash != manifest["corpus_fact_id_hash"]:
        drift.append({
            "what": "corpus",
            "manifest_hash": manifest["corpus_fact_id_hash"],
            "current_hash": current_hash,
            "expected_count": manifest["corpus_fact_count"],
            "current_count": len(current_fact_ids),
        })
    if current_code != manifest["code_hash"]:
        drift.append({
            "what": "code",
            "manifest_hash": manifest["code_hash"],
            "current_hash": current_code,
            "note": "Scoring/collision code changed since pre-registration. "
                    "Any results after this point are EXPLORATORY, not confirmatory.",
        })
    current_strata = _count_by_stratum(current_fact_ids)
    for s in ["A", "B", "C", "D"]:
        expected = manifest["strata"][s]["n_in_corpus"]
        actual = current_strata[s]
        if expected != actual:
            drift.append({
                "what": f"stratum_{s}",
                "expected": expected,
                "actual": actual,
            })

    return {
        "status": "ok" if not drift else "drift",
        "drift": drift,
        "manifest_created": manifest["created_at"],
    }


def status():
    if MANIFEST_PATH.exists():
        m = json.loads(MANIFEST_PATH.read_text())
        print(f"✓ Pre-registration exists: {m['created_at']}")
        print(f"  Corpus cutoff: {m['corpus_cutoff']}")
        print(f"  Corpus size:   {m['corpus_fact_count']} facts")
        print(f"  Code hash:     {m['code_hash']}")
        print(f"\n  Strata:")
        for s, info in m["strata"].items():
            print(f"    {s}: n={info['n_in_corpus']:>4}  {info['criterion']}  →  {info['expected_alpha_sign']}")
        v = verify_manifest()
        if v["status"] == "ok":
            print(f"\n  Verify: ✓ no drift")
        else:
            print(f"\n  Verify: ⚠ DRIFT DETECTED")
            for d in v["drift"]:
                print(f"    - {d}")
        return

    # Preview what a new manifest would look like
    preview = _build_manifest()
    print("No preregistration.json yet. Preview of what would be locked:")
    print(f"  Corpus cutoff:  {preview['corpus_cutoff']}")
    print(f"  Corpus size:    {preview['corpus_fact_count']} facts")
    print(f"  Holdout start:  {preview['holdout_start']}")
    print(f"\n  Strata (collisions with all facts pre-cutoff | majority pre-cutoff):")
    partial_map = preview.get("strata_partial", {"A": 0, "B": 0, "C": 0, "D": 0})
    for s, info in preview["strata"].items():
        strict = info["n_in_corpus"]
        partial = partial_map.get(s, 0)
        marker = "✓" if strict >= 30 else "⚠"
        print(f"    {s}: strict={strict:>4}  partial={partial:>4}  {info['criterion']:>20}  {marker}")
    print("\n  Note: strict=0 for all strata is expected — existing collisions mix")
    print("  pre/post-cutoff facts. For the summer study you'll regenerate")
    print("  collisions from the frozen pre-cutoff corpus only.")
    print(f"\n  Power: {'SUFFICIENT' if preview['power_analysis']['current_sufficient'] else 'INSUFFICIENT — run more cycles'}")
    print(f"  (Run `python preregister.py write` to lock)")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "write":
        cutoff = sys.argv[2] if len(sys.argv) > 2 else CORPUS_CUTOFF
        m = write_manifest(cutoff=cutoff)
        if m:
            print(f"✓ Pre-registration locked: {MANIFEST_PATH}")
            print(f"  Corpus cutoff:  {m['corpus_cutoff']}")
            print(f"  Corpus size:    {m['corpus_fact_count']} facts")
            print(f"  Strata: " + ", ".join(f"{k}={v['n_in_corpus']}" for k, v in m["strata"].items()))
            print(f"  Code hash:      {m['code_hash']}")
            print(f"\n  Do not modify scoring, collision, or fact code before study end.")
            print(f"  Run `python preregister.py verify` weekly to check drift.")
    elif cmd == "verify":
        v = verify_manifest()
        print(json.dumps(v, indent=2))
    else:
        status()
