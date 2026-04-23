"""Tests for the thesis-deduplication core in thesis_dedup.py.

Skipped gracefully if sentence_transformers is not installed in the test env.
"""

import pytest


def _import_or_skip():
    try:
        from thesis_dedup import _thesis_core
        return _thesis_core
    except ImportError:
        pytest.skip("sentence_transformers not available")


class TestThesisDedup:
    def test_identity(self):
        _thesis_core = _import_or_skip()
        a = _thesis_core("XYZ thesis about CMBS", "Buy REIT")
        b = _thesis_core("XYZ thesis about CMBS", "Buy REIT")
        assert a == b

    def test_long_text_truncates(self):
        _thesis_core = _import_or_skip()
        long_text = "x" * 2000
        result = _thesis_core(long_text, "")
        assert len(result) <= 1250

    def test_different_texts_produce_different_cores(self):
        _thesis_core = _import_or_skip()
        a = _thesis_core("CMBS office distress thesis", "Short")
        b = _thesis_core("Pharma DCF stale assumptions", "Long")
        assert a != b

    def test_empty_input_returns_string(self):
        _thesis_core = _import_or_skip()
        result = _thesis_core("", "")
        assert isinstance(result, str)
