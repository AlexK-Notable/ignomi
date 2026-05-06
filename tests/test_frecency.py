"""
Tests for the frecency score calculation and database operations.

Uses real SQLite databases. Ignis/GTK module mocks are installed by
conftest.py.
"""

import sqlite3
import time
from unittest.mock import MagicMock

import pytest

from services.frecency import FrecencyService


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
