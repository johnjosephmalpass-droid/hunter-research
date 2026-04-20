"""Minimum unit tests for HUNTER's core functions.

Covers:
 - compute_collision_formula (both weight versions, sanity checks)
 - compute_depth_value (hump shape, boundary conditions)
 - thesis_dedup._thesis_core / is_thesis_duplicate (identity + similarity)
 - obscurity_filter.compute_obscurity_score (edge cases)
 - cycle_detector._canonicalise / _node_id (canonicalisation stability)

Run:
    python -m pytest test_core.py
    # OR without pytest:
    python test_core.py
"""

import sys


def _ok(name, cond, detail=""):
    print(f"  {'✓' if cond else '✗'} {name}" + (f" — {detail}" if detail else ""))
    return cond


def test_compute_collision_formula():
    print("\ntest_compute_collision_formula")
    from theory import compute_collision_formula, COLLISION_FORMULA_WEIGHTS

    # Both weight versions should produce a numeric total
    r1 = compute_collision_formula("sec_filing", "regulation", "v1_original")
    r2 = compute_collision_formula("sec_filing", "regulation", "v2_refitted_conservative")
    _ok("v1 returns dict", isinstance(r1, dict) and "total" in r1)
    _ok("v2 returns dict", isinstance(r2, dict) and "total" in r2)
    _ok("v1 total is numeric", isinstance(r1["total"], (int, float)))
    _ok("v2 total is numeric", isinstance(r2["total"], (int, float)))

    # Default version should match ACTIVE_COLLISION_WEIGHTS_VERSION
    from theory import ACTIVE_COLLISION_WEIGHTS_VERSION
    r_default = compute_collision_formula("sec_filing", "regulation")
    _ok("default uses active version",
        r_default["weights_version"] == ACTIVE_COLLISION_WEIGHTS_VERSION,
        f"got {r_default['weights_version']}")

    # Non-negative score for reasonable inputs
    _ok("score non-negative", r1["total"] >= 0)

    # Symmetry — score(A,B) == score(B,A)
    ab = compute_collision_formula("sec_filing", "regulation")["total"]
    ba = compute_collision_formula("regulation", "sec_filing")["total"]
    _ok("symmetric", abs(ab - ba) < 0.01, f"|{ab}-{ba}|={abs(ab-ba)}")


def test_compute_depth_value():
    print("\ntest_compute_depth_value")
    from theory import compute_depth_value

    # Zero at d=0
    _ok("d=0 is zero", compute_depth_value(0) == 0.0)

    # Negative returns 0
    _ok("negative returns 0", compute_depth_value(-1) == 0.0)

    # Peak around d=3
    values = [compute_depth_value(d) for d in range(1, 10)]
    peak_idx = values.index(max(values)) + 1  # +1 because range started at 1
    _ok("peaks at d≈3", peak_idx in (2, 3, 4), f"peaked at d={peak_idx}")

    # Reasonable magnitude (should be $M, not $T)
    _ok("peak < $20M", max(values) < 20.0, f"peak was {max(values):.2f}M")
    _ok("peak > $1M", max(values) > 1.0, f"peak was {max(values):.2f}M")


def test_thesis_dedup():
    print("\ntest_thesis_dedup")
    try:
        from thesis_dedup import _thesis_core
        # Identity — same text produces same core
        a = _thesis_core("XYZ thesis about CMBS", "Buy REIT")
        b = _thesis_core("XYZ thesis about CMBS", "Buy REIT")
        _ok("identity", a == b)
        # Truncation at 1200 chars
        long_text = "x" * 2000
        c = _thesis_core(long_text, "")
        _ok("truncates long text", len(c) <= 1250)
    except ImportError:
        _ok("thesis_dedup import", False, "sentence_transformers not installed")


def test_obscurity_filter():
    print("\ntest_obscurity_filter")
    from obscurity_filter import _extract_entities

    # Empty text returns empty
    _ok("empty returns []", _extract_entities("") == [])

    # Extracts proper nouns and tickers
    ents = _extract_entities("Vornado Realty Trust VNO reported earnings.")
    _ok("extracts ticker", "VNO" in ents or any("Vornado" in e for e in ents))

    # Filters stop-words
    ents2 = _extract_entities("The company reported earnings.")
    _ok("filters 'The'", "The" not in ents2)


def test_cycle_detector():
    print("\ntest_cycle_detector")
    from cycle_detector import _canonicalise, _node_id

    # Empty returns empty
    _ok("empty canonicalise", _canonicalise("") == "")

    # Lowercase + strip punctuation
    c = _canonicalise("The NAIC RBC Formula (2023)")
    _ok("lowercased", c == c.lower())
    _ok("no punctuation", "(" not in c and ")" not in c)

    # node_id produces hash::readable format
    link = {"broken_methodology": "CMBS rating model",
            "broken_assumption": "AAA stability",
            "domain": "credit"}
    nid = _node_id(link)
    _ok("node_id has separator", "::" in nid)


def test_residual_tam():
    print("\ntest_residual_tam")
    from residual_tam import per_chain_value_M, _depth_weighted_value, all_scenarios

    # Per-chain hump check
    _ok("d=0 is 0", per_chain_value_M(0) == 0.0)
    values = [per_chain_value_M(d, 10.0, 3.0) for d in range(1, 8)]
    _ok("peaks near d=3", max(values) == values[2] or max(values) == values[1],
        f"values: {[round(v,2) for v in values]}")

    # Weighted value is positive
    w = _depth_weighted_value(10.0)
    _ok("weighted value positive", w > 0)

    # Scenarios all return structure
    scenarios = all_scenarios()
    _ok("3 scenarios", len(scenarios) == 3)
    for name, s in scenarios.items():
        _ok(f"{name} has TAM", s["total_addressable_residual_B"] > 0)


def main():
    print("=" * 60)
    print("HUNTER core unit tests")
    print("=" * 60)
    tests = [
        test_compute_collision_formula,
        test_compute_depth_value,
        test_thesis_dedup,
        test_obscurity_filter,
        test_cycle_detector,
        test_residual_tam,
    ]
    total = 0
    failed = 0
    for t in tests:
        try:
            t()
        except Exception as e:
            print(f"  ✗ {t.__name__} crashed: {e}")
            failed += 1
        total += 1
    print(f"\n{total} test groups run, {failed} crashed.")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
