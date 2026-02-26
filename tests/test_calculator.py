"""
Tests for the calculator search handler.

Uses real simpleeval (no mocking). Tests math evaluation, error handling,
and safety (no access to builtins/os).
"""

import pytest
from unittest.mock import patch, MagicMock


# Mock the Ignis modules that calculator.py transitively imports
@pytest.fixture(autouse=True)
def _mock_ignis():
    with patch.dict("sys.modules", {
        "ignis": MagicMock(),
        "ignis.services": MagicMock(),
        "ignis.services.applications": MagicMock(),
    }):
        yield


class TestCalculatorMatches:
    """Test prefix matching for the = trigger."""

    def test_matches_equals_prefix(self):
        from search.handlers.calculator import CalculatorHandler
        h = CalculatorHandler()
        assert h.matches("= 2+2") is True

    def test_matches_bare_equals(self):
        from search.handlers.calculator import CalculatorHandler
        h = CalculatorHandler()
        assert h.matches("=") is True

    def test_no_match_without_prefix(self):
        from search.handlers.calculator import CalculatorHandler
        h = CalculatorHandler()
        assert h.matches("2+2") is False

    def test_no_match_empty(self):
        from search.handlers.calculator import CalculatorHandler
        h = CalculatorHandler()
        assert h.matches("") is False


class TestCalculatorResults:
    """Test math expression evaluation."""

    def test_basic_addition(self):
        from search.handlers.calculator import CalculatorHandler
        h = CalculatorHandler()
        results = h.get_results("= 2 + 3")
        assert len(results) == 1
        assert results[0].title == "5"

    def test_float_result(self):
        from search.handlers.calculator import CalculatorHandler
        h = CalculatorHandler()
        results = h.get_results("= 1 / 3")
        assert len(results) == 1
        assert "0.333" in results[0].title

    def test_integer_display_for_whole_floats(self):
        from search.handlers.calculator import CalculatorHandler
        h = CalculatorHandler()
        results = h.get_results("= 6 / 2")
        assert results[0].title == "3"

    def test_sqrt_function(self):
        from search.handlers.calculator import CalculatorHandler
        h = CalculatorHandler()
        results = h.get_results("= sqrt(16)")
        assert results[0].title == "4"

    def test_empty_expression_shows_help(self):
        from search.handlers.calculator import CalculatorHandler
        h = CalculatorHandler()
        results = h.get_results("=")
        assert len(results) == 1
        assert "expression" in results[0].title.lower() or "expression" in results[0].description.lower()

    def test_invalid_expression_shows_error(self):
        from search.handlers.calculator import CalculatorHandler
        h = CalculatorHandler()
        results = h.get_results("= !!!invalid")
        assert len(results) == 1
        assert "invalid" in results[0].title.lower() or "error" in results[0].title.lower()

    def test_malicious_import_rejected(self):
        from search.handlers.calculator import CalculatorHandler
        h = CalculatorHandler()
        results = h.get_results("= __import__('os').system('ls')")
        # Should return an error, not execute
        assert len(results) == 1
        assert results[0].result_type == "calculator"
        # Should not have a valid numeric title
        assert not results[0].title.isdigit()

    def test_pi_available_as_name(self):
        """pi and e are available as named constants (not callable functions)."""
        from search.handlers.calculator import CalculatorHandler
        h = CalculatorHandler()
        results = h.get_results("= pi * 2")
        assert len(results) == 1
        assert "6.28" in results[0].title

    def test_e_available_as_name(self):
        from search.handlers.calculator import CalculatorHandler
        h = CalculatorHandler()
        results = h.get_results("= e")
        assert len(results) == 1
        assert "2.71" in results[0].title

    def test_division_by_zero(self):
        from search.handlers.calculator import CalculatorHandler
        h = CalculatorHandler()
        results = h.get_results("= 1/0")
        assert len(results) == 1
        assert "error" in results[0].title.lower() or "math" in results[0].title.lower()
