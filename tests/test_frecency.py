"""
Tests for the frecency score calculation and database operations.

Uses real SQLite databases. Mocks only GObject signals and BaseService
to avoid GTK dependency.
"""

import sqlite3
import sys
import time
import types
from unittest.mock import MagicMock

import pytest


# Save original modules before patching
_saved_modules = {}
_modules_to_fake = ["gi", "gi.repository", "gi.repository.GObject",
                     "ignis", "ignis.base_service"]
for _mod in _modules_to_fake:
    if _mod in sys.modules:
        _saved_modules[_mod] = sys.modules[_mod]

# Create fake modules for headless testing
_fake_gi = types.ModuleType("gi")
_fake_gi_repo = types.ModuleType("gi.repository")
_fake_gobject = MagicMock()
_fake_gobject.SignalFlags.RUN_FIRST = 0
_fake_gi_repo.GObject = _fake_gobject
_fake_gi.repository = _fake_gi_repo

_fake_ignis = types.ModuleType("ignis")
_fake_base_service = types.ModuleType("ignis.base_service")


class _FakeBaseService:
    """Minimal BaseService stand-in that supports normal __init__."""
    def __init__(self):
        pass

    def emit(self, *args, **kwargs):
        pass


_fake_base_service.BaseService = _FakeBaseService
_fake_ignis.base_service = _fake_base_service

# Install fakes
sys.modules["gi"] = _fake_gi
sys.modules["gi.repository"] = _fake_gi_repo
sys.modules["gi.repository.GObject"] = _fake_gobject
sys.modules["ignis"] = _fake_ignis
sys.modules["ignis.base_service"] = _fake_base_service

# Import the module under test (uses fake dependencies)
from services.frecency import FrecencyService

# Restore original modules so other test files aren't affected
for _mod in _modules_to_fake:
    if _mod in _saved_modules:
        sys.modules[_mod] = _saved_modules[_mod]
    elif _mod in sys.modules:
        del sys.modules[_mod]


def _make_service(db_path):
    """Create a FrecencyService with emit mocked and persistent connection."""
    svc = FrecencyService.__new__(FrecencyService)
    svc.db_path = db_path
    svc._conn = sqlite3.connect(str(db_path))
    svc._conn.execute("PRAGMA journal_mode=WAL")
    svc.emit = MagicMock()
    svc._init_database()
    return svc


class TestFrecencyCalculation:
    """Test the _calculate_frecency scoring logic."""

    def test_recent_launch_gets_100x(self, tmp_db):
        svc = _make_service(tmp_db)
        now = time.time()
        score = svc._calculate_frecency(5, int(now - 3600))
        assert score == 500

    def test_week_old_launch_gets_70x(self, tmp_db):
        svc = _make_service(tmp_db)
        now = time.time()
        score = svc._calculate_frecency(3, int(now - 10 * 86400))
        assert score == 210

    def test_month_old_launch_gets_50x(self, tmp_db):
        svc = _make_service(tmp_db)
        now = time.time()
        score = svc._calculate_frecency(4, int(now - 20 * 86400))
        assert score == 200

    def test_quarter_old_launch_gets_30x(self, tmp_db):
        svc = _make_service(tmp_db)
        now = time.time()
        score = svc._calculate_frecency(2, int(now - 60 * 86400))
        assert score == 60

    def test_ancient_launch_gets_10x(self, tmp_db):
        svc = _make_service(tmp_db)
        now = time.time()
        score = svc._calculate_frecency(10, int(now - 120 * 86400))
        assert score == 100


class TestRecordLaunch:
    """Test recording app launches to the database."""

    def test_first_launch_creates_entry(self, tmp_db):
        svc = _make_service(tmp_db)
        svc.record_launch("firefox.desktop")

        conn = sqlite3.connect(str(tmp_db))
        row = conn.execute(
            "SELECT launch_count FROM app_stats WHERE app_id = ?",
            ("firefox.desktop",),
        ).fetchone()
        conn.close()
        assert row[0] == 1

    def test_second_launch_increments_count(self, tmp_db):
        svc = _make_service(tmp_db)
        svc.record_launch("firefox.desktop")
        svc.record_launch("firefox.desktop")

        conn = sqlite3.connect(str(tmp_db))
        row = conn.execute(
            "SELECT launch_count FROM app_stats WHERE app_id = ?",
            ("firefox.desktop",),
        ).fetchone()
        conn.close()
        assert row[0] == 2

    def test_record_launch_emits_changed(self, tmp_db):
        svc = _make_service(tmp_db)
        svc.record_launch("firefox.desktop")
        svc.emit.assert_called_with("changed")


class TestGetTopApps:
    """Test retrieving top apps by frecency score."""

    def test_empty_db_returns_empty_list(self, tmp_db):
        svc = _make_service(tmp_db)
        result = svc.get_top_apps()
        assert result == []

    def test_returns_sorted_by_frecency(self, tmp_db):
        svc = _make_service(tmp_db)
        now = int(time.time())

        conn = sqlite3.connect(str(tmp_db))
        conn.execute(
            "INSERT INTO app_stats VALUES (?, ?, ?, ?)",
            ("old.desktop", 10, now - 100 * 86400, now - 100 * 86400),
        )
        conn.execute(
            "INSERT INTO app_stats VALUES (?, ?, ?, ?)",
            ("new.desktop", 2, now - 3600, now - 3600),
        )
        conn.commit()
        conn.close()

        results = svc.get_top_apps(limit=10)
        assert results[0][0] == "new.desktop"
        assert results[1][0] == "old.desktop"

    def test_respects_min_launches(self, tmp_db):
        svc = _make_service(tmp_db)
        now = int(time.time())

        conn = sqlite3.connect(str(tmp_db))
        conn.execute(
            "INSERT INTO app_stats VALUES (?, ?, ?, ?)",
            ("once.desktop", 1, now, now),
        )
        conn.commit()
        conn.close()

        results = svc.get_top_apps(min_launches=2)
        assert len(results) == 0
