"""Tests for cycle detection in cycle_detector.py.

cycle_detector is one of the seven SHA-locked files. These tests pin its
canonicalisation behaviour.
"""

import pytest

from cycle_detector import _canonicalise, _node_id


class TestCanonicalise:
    def test_empty_returns_empty(self):
        assert _canonicalise("") == ""

    def test_lowercased(self):
        result = _canonicalise("The NAIC RBC Formula (2023)")
        assert result == result.lower()

    def test_strips_punctuation(self):
        result = _canonicalise("The NAIC RBC Formula (2023)")
        assert "(" not in result
        assert ")" not in result

    def test_idempotent(self):
        original = "CMBS Servicer Default Probability Models"
        once = _canonicalise(original)
        twice = _canonicalise(once)
        assert once == twice


class TestNodeId:
    def test_has_separator(self):
        link = {
            "broken_methodology": "CMBS rating model",
            "broken_assumption": "AAA stability",
            "domain": "credit",
        }
        nid = _node_id(link)
        assert "::" in nid

    def test_consistent_for_same_input(self):
        link = {
            "broken_methodology": "X",
            "broken_assumption": "Y",
            "domain": "z",
        }
        a = _node_id(link)
        b = _node_id(link)
        assert a == b
