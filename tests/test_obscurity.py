"""Tests for entity extraction in obscurity_filter.py."""

import pytest

from obscurity_filter import _extract_entities


class TestEntityExtraction:
    def test_empty_text_returns_empty(self):
        assert _extract_entities("") == []

    def test_extracts_ticker(self):
        ents = _extract_entities("Vornado Realty Trust VNO reported earnings.")
        assert "VNO" in ents or any("Vornado" in e for e in ents)

    def test_filters_stop_word_the(self):
        ents = _extract_entities("The company reported earnings.")
        assert "The" not in ents

    def test_filters_common_words(self):
        ents = _extract_entities("This is a test of the system.")
        for stopword in ["This", "The", "is", "a"]:
            assert stopword not in ents

    def test_extracts_proper_nouns(self):
        ents = _extract_entities("Apple Inc and Microsoft Corp announced a partnership.")
        assert any("Apple" in e for e in ents) or "AAPL" in ents
        assert any("Microsoft" in e for e in ents) or "MSFT" in ents
