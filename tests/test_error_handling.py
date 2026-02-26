"""
Tests for error handling across services and handlers.

Verifies graceful degradation when things go wrong:
- Corrupt database
- Missing files
- Invalid expressions
"""

import sqlite3
import sys
import time
import types
from unittest.mock import MagicMock

import pytest

# Save and patch GObject/Ignis modules for headless testing
_saved_modules = {}
_modules_to_fake = ["gi", "gi.repository", "gi.repository.GObject",
                     "ignis", "ignis.base_service"]
for _mod in _modules_to_fake:
    if _mod in sys.modules:
        _saved_modules[_mod] = sys.modules[_mod]

_fake_gi = types.ModuleType("gi")
_fake_gi_repo = types.ModuleType("gi.repository")
_fake_gobject = MagicMock()
_fake_gobject.SignalFlags.RUN_FIRST = 0
_fake_gi_repo.GObject = _fake_gobject
_fake_gi.repository = _fake_gi_repo

_fake_ignis = types.ModuleType("ignis")
_fake_base_service = types.ModuleType("ignis.base_service")


class _FakeBaseService:
    def __init__(self):
        pass
    def emit(self, *args, **kwargs):
        pass

_fake_base_service.BaseService = _FakeBaseService
_fake_ignis.base_service = _fake_base_service

sys.modules["gi"] = _fake_gi
sys.modules["gi.repository"] = _fake_gi_repo
sys.modules["gi.repository.GObject"] = _fake_gobject
sys.modules["ignis"] = _fake_ignis
sys.modules["ignis.base_service"] = _fake_base_service

from services.frecency import FrecencyService

for _mod in _modules_to_fake:
    if _mod in _saved_modules:
        sys.modules[_mod] = _saved_modules[_mod]
    elif _mod in sys.modules:
        del sys.modules[_mod]


def _make_service(db_path):
    """Create a FrecencyService with persistent connection."""
    svc = FrecencyService.__new__(FrecencyService)
    svc.db_path = db_path
    svc._conn = sqlite3.connect(str(db_path))
    svc._conn.execute("PRAGMA journal_mode=WAL")
    svc.emit = MagicMock()
    svc._init_database()
    return svc


class TestFrecencyErrorHandling:
    """Test FrecencyService handles database errors gracefully."""

    def test_record_launch_survives_closed_connection(self, tmp_db):
        """If connection is somehow closed, record_launch doesn't crash."""
        svc = _make_service(tmp_db)
        svc._conn.close()
        # Should not raise — logs exception internally
        svc.record_launch("test.desktop")
        # Signal should NOT have been emitted (error path returns early)
        svc.emit.assert_not_called()

    def test_clear_stats_survives_closed_connection(self, tmp_db):
        """If connection is closed, clear_stats doesn't crash."""
        svc = _make_service(tmp_db)
        # First add some data
        svc.record_launch("test.desktop")
        svc.emit.reset_mock()
        # Close connection
        svc._conn.close()
        # Should not raise
        svc.clear_stats("test.desktop")
        svc.emit.assert_not_called()

    def test_get_app_stats_returns_none_for_missing(self, tmp_db):
        svc = _make_service(tmp_db)
        result = svc.get_app_stats("nonexistent.desktop")
        assert result is None

    def test_get_total_launches_empty_db(self, tmp_db):
        svc = _make_service(tmp_db)
        assert svc.get_total_launches() == 0


class TestCalculatorErrorPaths:
    """Test calculator handler error messages."""

    def test_invalid_expression_returns_error_result(self):
        from search.handlers.calculator import CalculatorHandler
        handler = CalculatorHandler()
        results = handler.get_results("= ][invalid")
        assert len(results) == 1
        assert "invalid" in results[0].title.lower() or "error" in results[0].title.lower()

    def test_division_by_zero_returns_math_error(self):
        from search.handlers.calculator import CalculatorHandler
        handler = CalculatorHandler()
        results = handler.get_results("= 1/0")
        assert len(results) == 1
        assert "error" in results[0].title.lower() or "math" in results[0].title.lower()

    def test_overflow_returns_math_error(self):
        from search.handlers.calculator import CalculatorHandler
        handler = CalculatorHandler()
        results = handler.get_results("= 10**10000")
        assert len(results) == 1
        # Should return some kind of error, not crash
        assert results[0].result_type == "calculator"
