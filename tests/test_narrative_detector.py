"""Tests for the narrative-strength scorer in narrative_detector.py."""

import pytest

from narrative_detector import _match_density, score_narrative


class TestMatchDensity:
    def test_empty_text_returns_zero(self):
        assert _match_density("", [r"\btest\b"]) == 0.0

    def test_capped_at_one(self):
        # Many distinct matches should cap at 1.0 (function uses set, so duplicates don't count)
        text = "alpha beta gamma delta epsilon zeta"
        result = _match_density(text, [r"\b[a-z]+\b"], cap=3)
        assert result == 1.0

    def test_unique_matches_normalised_by_cap(self):
        # 1 unique match, cap=3 -> 1/3
        text = "test test test test"
        result = _match_density(text, [r"\btest\b"], cap=3)
        assert abs(result - 1.0 / 3) < 1e-6

    def test_no_matches_returns_zero(self):
        result = _match_density("hello world", [r"\bfoobar\b"])
        assert result == 0.0


class TestNarrativeStrength:
    def test_returns_score_dict(self):
        result = score_narrative("CMBS office mispricing in 2026 due to NAIC reserve changes.")
        assert isinstance(result, dict)
        assert "narrative_strength" in result

    def test_score_in_range(self):
        result = score_narrative("Some financial thesis about a regulator action in 2026.")
        assert 0.0 <= result["narrative_strength"] <= 1.0

    def test_empty_text_returns_low_score(self):
        result = score_narrative("")
        assert result["narrative_strength"] == 0.0

    def test_high_signal_text_scores_higher_than_low(self):
        high = score_narrative(
            "NAIC mispricing of CMBS in Q1 2026 will trigger a downgrade by March 2026 "
            "as Cleveland-Cliffs Inc faces OSHA compliance costs."
        )
        low = score_narrative("Things might happen in finance.")
        assert high["narrative_strength"] > low["narrative_strength"]

    def test_components_present(self):
        result = score_narrative("test thesis with NAIC and 2026 catalyst")
        for component in ("protagonist", "antagonist", "complication", "catalyst", "resolution"):
            assert component in result
