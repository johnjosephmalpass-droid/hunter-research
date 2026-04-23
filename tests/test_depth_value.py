"""Tests for the depth-value hump function in theory.py."""

import pytest

from theory import compute_depth_value


class TestDepthValue:
    def test_d_zero_returns_zero(self):
        assert compute_depth_value(0) == 0.0

    def test_negative_returns_zero(self):
        assert compute_depth_value(-1) == 0.0
        assert compute_depth_value(-100) == 0.0

    def test_peaks_around_d_3(self):
        values = [compute_depth_value(d) for d in range(1, 10)]
        peak_idx = values.index(max(values)) + 1
        assert peak_idx in (2, 3, 4), f"peaked at d={peak_idx}, expected 2-4"

    def test_peak_in_reasonable_magnitude(self):
        values = [compute_depth_value(d) for d in range(1, 10)]
        peak = max(values)
        assert 1.0 < peak < 20.0, f"peak was {peak}, expected $1M to $20M"

    def test_decays_after_peak(self):
        v8 = compute_depth_value(8)
        v3 = compute_depth_value(3)
        assert v8 < v3, "value should decay between d=3 and d=8"

    def test_monotonic_decay_after_peak(self):
        # After the peak, each step should be smaller than the previous
        values = [compute_depth_value(d) for d in range(3, 10)]
        for i in range(1, len(values)):
            assert values[i] <= values[i - 1] * 1.05, f"non-monotonic decay at d={i+3}"
