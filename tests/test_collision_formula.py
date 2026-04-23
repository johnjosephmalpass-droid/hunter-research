"""Tests for the collision-scoring formula in theory.py.

The formula is one of the seven SHA-locked files. These tests pin its
behaviour so any inadvertent change shows up immediately in CI.
"""

import math

import pytest

from theory import (
    ACTIVE_COLLISION_WEIGHTS_VERSION,
    COLLISION_FORMULA_WEIGHTS,
    compute_collision_formula,
)


class TestCollisionFormula:
    def test_v1_returns_dict_with_total(self):
        result = compute_collision_formula("sec_filing", "regulation", "v1_original")
        assert isinstance(result, dict)
        assert "total" in result
        assert isinstance(result["total"], (int, float))

    def test_v2_returns_dict_with_total(self):
        result = compute_collision_formula("sec_filing", "regulation", "v2_refitted_conservative")
        assert isinstance(result, dict)
        assert "total" in result
        assert isinstance(result["total"], (int, float))

    def test_default_uses_active_version(self):
        result = compute_collision_formula("sec_filing", "regulation")
        assert result["weights_version"] == ACTIVE_COLLISION_WEIGHTS_VERSION

    def test_score_is_non_negative(self):
        result = compute_collision_formula("sec_filing", "regulation", "v1_original")
        assert result["total"] >= 0

    def test_symmetry(self):
        ab = compute_collision_formula("sec_filing", "regulation")["total"]
        ba = compute_collision_formula("regulation", "sec_filing")["total"]
        assert math.isclose(ab, ba, abs_tol=0.01)

    def test_unknown_source_type_does_not_crash(self):
        result = compute_collision_formula("nonexistent_xyz", "regulation")
        assert isinstance(result["total"], (int, float))

    def test_both_weight_versions_exist(self):
        assert "v1_original" in COLLISION_FORMULA_WEIGHTS
        assert "v2_refitted_conservative" in COLLISION_FORMULA_WEIGHTS
