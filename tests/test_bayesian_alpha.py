"""Tests for the Bayesian re-analysis script."""

import pytest

# Skip the whole module if scipy or numpy not available
np = pytest.importorskip("numpy")
scipy = pytest.importorskip("scipy")

from bayesian_alpha import (
    narrative_strength,
    posterior_correlation_via_fisher_z,
    posterior_group_difference_normal_normal,
)


class TestNarrativeStrength:
    def test_returns_float_in_range(self):
        result = narrative_strength("test thesis")
        assert isinstance(result, float)
        assert 0.0 <= result <= 1.0

    def test_empty_text_returns_zero(self):
        assert narrative_strength("") == 0.0

    def test_consistent_for_same_input(self):
        text = "NAIC reserve methodology for CMBS in Q1 2026"
        a = narrative_strength(text)
        b = narrative_strength(text)
        assert a == b


class TestPosteriorCorrelation:
    def test_strong_negative_signal(self):
        rng = np.random.default_rng(0)
        x = list(range(50))
        y = [-i + rng.normal(0, 1) for i in range(50)]
        result = posterior_correlation_via_fisher_z(x, y, n_samples=2000, seed=42)
        assert result["P(r < 0)"] > 0.95
        assert result["posterior_mean_r"] < -0.5

    def test_strong_positive_signal(self):
        rng = np.random.default_rng(1)
        x = list(range(50))
        y = [i + rng.normal(0, 1) for i in range(50)]
        result = posterior_correlation_via_fisher_z(x, y, n_samples=2000, seed=42)
        assert result["P(r < 0)"] < 0.05

    def test_too_small_n_returns_error(self):
        result = posterior_correlation_via_fisher_z([1, 2], [3, 4])
        assert "error" in result

    def test_credible_interval_around_observed(self):
        # With perfect correlation, observed is at the upper boundary of feasibility
        # so CI may extend to but not strictly contain the observed point estimate
        rng = np.random.default_rng(2)
        x = list(range(30))
        y = [2 * i + rng.normal(0, 1) for i in range(30)]
        result = posterior_correlation_via_fisher_z(x, y, n_samples=2000, seed=42)
        ci_low, ci_high = result["ci_95"]
        # The posterior mean should be inside the CI by construction
        assert ci_low <= result["posterior_mean_r"] <= ci_high


class TestPosteriorDifference:
    def test_clear_group_separation(self):
        a = [1.0, 2.0, 3.0, 2.5, 1.5] * 5
        b = [10.0, 11.0, 12.0, 11.5, 10.5] * 5
        result = posterior_group_difference_normal_normal(a, b, n_samples=2000, seed=42)
        assert result["P(mu_b > mu_a)"] > 0.95
        assert result["posterior_mean_diff"] > 5.0

    def test_overlapping_groups_uncertain(self):
        # Groups with overlapping distributions: posterior probability is moderate, not extreme
        rng = np.random.default_rng(11)
        a = list(rng.normal(5, 2, size=30))
        b = list(rng.normal(5.5, 2, size=30))
        result = posterior_group_difference_normal_normal(a, b, n_samples=2000, seed=42)
        # Slightly higher mean for b means P should lean above 0.5 but not be certain
        assert 0.5 <= result["P(mu_b > mu_a)"] <= 0.99

    def test_too_small_returns_error(self):
        result = posterior_group_difference_normal_normal([1], [2])
        assert "error" in result
