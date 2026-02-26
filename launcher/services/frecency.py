"""
Frecency Service - Track and rank applications by usage frequency and recency.

Implements a Firefox-style frecency algorithm:
  frecency_score = launch_count * recency_weight

Where recency_weight depends on how recently the app was launched:
  - < 4 days: 100x multiplier
  - < 14 days: 70x multiplier
  - < 31 days: 50x multiplier
  - < 90 days: 30x multiplier
  - 90+ days: 10x multiplier

This ensures recently-used apps rank higher than frequently-but-old apps.
"""

import sqlite3
import time
from pathlib import Path

from gi.repository import GObject
from ignis.base_service import BaseService
from loguru import logger


class FrecencyService(BaseService):
    """
    Service for tracking application usage and calculating frecency scores.

    Signals:
        changed: Emitted when app usage data changes (after record_launch)

    Methods:
        record_launch(app_id): Record an app launch
        get_top_apps(limit): Get top N apps by frecency score
    """

    __gtype_name__ = "FrecencyService"

    __gsignals__ = {
        "changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self):
        super().__init__()

        # Database location (XDG standard)
        data_dir = Path.home() / ".local" / "share" / "ignomi"
        data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = data_dir / "app_usage.db"

        # Persistent connection with WAL mode for better concurrency
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._init_database()
        logger.debug(f"FrecencyService initialized with db at {self.db_path}")

    def _init_database(self):
        """Create database schema if it doesn't exist."""
        cursor = self._conn.cursor()

        # Create app_stats table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS app_stats (
                app_id TEXT PRIMARY KEY,
                launch_count INTEGER DEFAULT 0,
                last_launch INTEGER,
                created_at INTEGER
            )
        """)

        # Create index for faster frecency queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_frecency
            ON app_stats(last_launch DESC, launch_count DESC)
        """)

        self._conn.commit()

    def record_launch(self, app_id: str) -> None:
        """
        Record an application launch.

        Args:
            app_id: Desktop file ID (e.g., "firefox.desktop")

        Emits:
            changed: Signal to notify listeners that data has updated
        """
        now = int(time.time())

        try:
            cursor = self._conn.cursor()

            # Insert new entry or update existing
            cursor.execute("""
                INSERT INTO app_stats (app_id, launch_count, last_launch, created_at)
                VALUES (?, 1, ?, ?)
                ON CONFLICT(app_id) DO UPDATE SET
                    launch_count = launch_count + 1,
                    last_launch = excluded.last_launch
            """, (app_id, now, now))

            self._conn.commit()

            logger.debug(f"Recorded launch for {app_id}")
        except sqlite3.Error:
            logger.exception(f"Failed to record launch for {app_id}")
            return

        # Notify listeners (frequent panel will refresh)
        self.emit("changed")

    def get_top_apps(self, limit: int = 12, min_launches: int = 1) -> list[tuple[str, float, int, int]]:
        """
        Get top applications ranked by frecency score.

        Args:
            limit: Maximum number of apps to return
            min_launches: Minimum launch count to include app

        Returns:
            List of tuples: (app_id, frecency_score, launch_count, last_launch)
            Sorted by frecency_score descending
        """
        cursor = self._conn.cursor()

        # Get all apps meeting minimum launch requirement
        cursor.execute("""
            SELECT app_id, launch_count, last_launch
            FROM app_stats
            WHERE launch_count >= ?
            ORDER BY last_launch DESC, launch_count DESC
        """, (min_launches,))

        results = []
        for app_id, launch_count, last_launch in cursor.fetchall():
            # Calculate frecency score
            score = self._calculate_frecency(launch_count, last_launch)
            results.append((app_id, score, launch_count, last_launch))

        # Sort by frecency score (descending)
        results.sort(key=lambda x: x[1], reverse=True)

        # Return top N
        return results[:limit]

    def get_app_stats(self, app_id: str) -> tuple[int, int, int] | None:
        """
        Get statistics for a specific app.

        Args:
            app_id: Desktop file ID

        Returns:
            Tuple of (launch_count, last_launch, created_at) or None if not found
        """
        cursor = self._conn.cursor()
        cursor.execute("""
            SELECT launch_count, last_launch, created_at
            FROM app_stats
            WHERE app_id = ?
        """, (app_id,))

        row = cursor.fetchone()
        return row if row else None

    def _calculate_frecency(self, launch_count: int, last_launch: int) -> float:
        """
        Calculate frecency score using Firefox's algorithm.

        Recent launches get higher weight multipliers:
          - Last 4 days: 100x
          - Last 14 days: 70x
          - Last 31 days: 50x
          - Last 90 days: 30x
          - Older: 10x

        Args:
            launch_count: Number of times app has been launched
            last_launch: Unix timestamp of last launch

        Returns:
            Frecency score (float)
        """
        now = time.time()
        age_seconds = now - last_launch
        age_days = age_seconds / (24 * 3600)

        # Determine recency weight based on age buckets
        if age_days < 4:
            recency_weight = 100
        elif age_days < 14:
            recency_weight = 70
        elif age_days < 31:
            recency_weight = 50
        elif age_days < 90:
            recency_weight = 30
        else:
            recency_weight = 10

        # Frecency = frequency × recency
        return launch_count * recency_weight

    def get_total_launches(self) -> int:
        """
        Get total number of app launches tracked.

        Returns:
            Total launch count across all apps
        """
        cursor = self._conn.cursor()
        cursor.execute("SELECT SUM(launch_count) FROM app_stats")
        result = cursor.fetchone()
        return result[0] if result[0] else 0

    def clear_stats(self, app_id: str | None = None) -> None:
        """
        Clear usage statistics.

        Args:
            app_id: If provided, clear only this app's stats.
                   If None, clear all stats.

        Emits:
            changed: Signal to notify listeners
        """
        try:
            cursor = self._conn.cursor()

            if app_id:
                cursor.execute("DELETE FROM app_stats WHERE app_id = ?", (app_id,))
            else:
                cursor.execute("DELETE FROM app_stats")

            self._conn.commit()
        except sqlite3.Error:
            logger.exception(f"Failed to clear stats for {app_id or 'all apps'}")
            return

        self.emit("changed")


# Singleton accessor
_frecency_service_instance = None


def get_frecency_service() -> FrecencyService:
    """
    Get the singleton FrecencyService instance.

    Returns:
        FrecencyService: The global instance
    """
    global _frecency_service_instance
    if _frecency_service_instance is None:
        _frecency_service_instance = FrecencyService()
    return _frecency_service_instance
