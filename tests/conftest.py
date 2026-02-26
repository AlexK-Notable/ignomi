"""
Shared test fixtures for the Ignomi launcher test suite.

Provides temporary database, bookmarks, settings, and commands files
that use real file I/O (no mocking of the filesystem).
"""

import json
import sqlite3
from pathlib import Path

import pytest
import toml


@pytest.fixture
def tmp_db(tmp_path):
    """Create a real SQLite database with FrecencyService-compatible schema."""
    db_path = tmp_path / "app_usage.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS app_stats (
            app_id TEXT PRIMARY KEY,
            launch_count INTEGER DEFAULT 0,
            last_launch INTEGER,
            created_at INTEGER
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_frecency
        ON app_stats(last_launch DESC, launch_count DESC)
    """)
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def tmp_bookmarks(tmp_path):
    """Create a real bookmarks JSON file with test entries."""
    bookmarks_path = tmp_path / "bookmarks.json"
    data = {
        "bookmarks": [
            "firefox.desktop",
            "code.desktop",
            "nautilus.desktop",
        ]
    }
    bookmarks_path.write_text(json.dumps(data, indent=2))
    return bookmarks_path


@pytest.fixture
def tmp_settings(tmp_path):
    """Create a real settings TOML file with all sections."""
    settings_path = tmp_path / "settings.toml"
    data = {
        "launcher": {"close_delay_ms": 300},
        "frecency": {"max_items": 12, "min_launches": 2},
        "search": {"max_results": 30, "fuzzy_threshold": 50},
        "animation": {"transition_duration": 200},
    }
    settings_path.write_text(toml.dumps(data))
    return settings_path


@pytest.fixture
def tmp_commands(tmp_path):
    """Create a real commands TOML file with test entries."""
    commands_path = tmp_path / "commands.toml"
    data = {
        "commands": {
            "lock": {
                "description": "Lock screen",
                "exec": "hyprlock",
                "icon": "system-lock-screen",
            },
            "suspend": {
                "description": "Suspend system",
                "exec": "systemctl suspend",
                "icon": "system-suspend",
            },
        }
    }
    commands_path.write_text(toml.dumps(data))
    return commands_path
