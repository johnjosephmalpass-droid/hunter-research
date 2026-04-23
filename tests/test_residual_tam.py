"""Tests for residual TAM scenario calculations."""

import pytest

from residual_tam import (
    _depth_weighted_value,
    all_scenarios,
    per_chain_value_M,
)


class TestPerChainValue:
    def test_d_zero_is_zero(self):
        assert per_chain_value_M(0) == 0.0

    def test_peaks_near_d_3(self):
        values = [per_chain_value_M(d, 10.0, 3.0) for d in range(1, 8)]
        peak_idx = values.index(max(values))
        assert peak_idx in (1, 2, 3), f"peak at index {peak_idx}, expected 1-3"

    def test_decays_after_peak(self):
        assert per_chain_value_M(7) < per_chain_value_M(3)

    def test_positive_for_positive_depth(self):
        for d in range(1, 10):
            assert per_chain_value_M(d) > 0


class TestDepthWeightedValue:
    def test_positive(self):
        w = _depth_weighted_value(10.0)
        assert w > 0


class TestAllScenarios:
    def test_three_scenarios_returned(self):
        scenarios = all_scenarios()
        assert len(scenarios) == 3

    def test_all_have_tam(self):
        scenarios = all_scenarios()
        for name, scenario in scenarios.items():
            assert scenario["total_addressable_residual_B"] > 0, f"{name} TAM should be positive"

    def test_scenarios_ordered_conservative_to_optimistic(self):
        scenarios = all_scenarios()
        c = scenarios["conservative"]["total_addressable_residual_B"]
        m = scenarios["central"]["total_addressable_residual_B"]
        o = scenarios["optimistic"]["total_addressable_residual_B"]
        assert c < m < o, f"expected ordering c < m < o, got {c}, {m}, {o}"
