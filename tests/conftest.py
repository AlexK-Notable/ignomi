"""
Shared test fixtures + module-level Ignis/GTK mocks for the Ignomi test suite.

The Ignomi runtime imports ignis.* and gi.repository.* at module load time.
On a headless box (CI, dev container, non-Wayland session) those imports
either fail (ImportError) or hang (display-server probe). Tests cannot
sidestep this by mocking inside fixtures, because pytest discovers and
imports test modules BEFORE any fixture runs — by which point the SUT's
own `from ignis.x import y` has already executed.

The fix is to install fake modules into ``sys.modules`` HERE, at conftest
collection time. ``conftest.py`` is loaded before any test module in the
same directory, so by the time a test does ``from services.frecency import
FrecencyService`` the fakes are already in place and the import succeeds.

The fakes are intentionally minimal — just enough that ``import`` succeeds
and that two specific places where SUTs read attribute shapes get the
expected types:

  * ``gi.repository.GObject.SignalFlags.RUN_FIRST`` → integer-like.
  * ``ignis.base_service.BaseService`` → a real class FrecencyService can
    inherit from (NOT a ``MagicMock``).

Everything else is a ``MagicMock`` that returns plausibly-shaped values.

We do NOT restore originals. The test process never wants the real
ignis/gi modules; restoration was the source of ~150 LOC of repeated
boilerplate across five test files (the prior Pattern-1 approach).
"""

import json
import sqlite3
import sys
import types
from unittest.mock import MagicMock

import pytest
import toml


# ---------------------------------------------------------------------------
# Module-level fakes (installed once, at conftest collection time).
# ---------------------------------------------------------------------------

class _FakeBaseService:
    """Real class so FrecencyService(BaseService) is a valid subclass."""
    def __init__(self):
        pass

    def emit(self, *args, **kwargs):
        pass


# gi + gi.repository
_fake_gi = types.ModuleType("gi")
_fake_gi_repo = types.ModuleType("gi.repository")

_fake_gobject = MagicMock()
_fake_gobject.SignalFlags.RUN_FIRST = 0
_fake_gi_repo.GObject = _fake_gobject
_fake_gi_repo.Gdk = MagicMock()
_fake_gi_repo.GLib = MagicMock()
_fake_gi_repo.Gtk = MagicMock()
_fake_gi_repo.GdkPixbuf = MagicMock()
_fake_gi.repository = _fake_gi_repo

# ignis + subpackages — set __path__ so it's treated as a package, allowing
# submodule imports like `from ignis.menu_model import IgnisMenuItem`.
_fake_ignis = types.ModuleType("ignis")
_fake_ignis.__path__ = []  # makes it a package
_fake_ignis.widgets = MagicMock()
_fake_ignis.app = MagicMock()
_fake_ignis.menu_model = MagicMock()

_fake_services = types.ModuleType("ignis.services")
_fake_services.__path__ = []
_fake_apps = types.ModuleType("ignis.services.applications")
_fake_apps_service = MagicMock()
_fake_apps_service.apps = []
_fake_apps.ApplicationsService = MagicMock()
_fake_apps.ApplicationsService.get_default.return_value = _fake_apps_service
_fake_hyprland = types.ModuleType("ignis.services.hyprland")
_fake_hyprland.HyprlandService = MagicMock()
_fake_audio = types.ModuleType("ignis.services.audio")
_fake_backlight = types.ModuleType("ignis.services.backlight")
_fake_systemd = types.ModuleType("ignis.services.systemd")
_fake_systemd.SystemdService = MagicMock()

_fake_services.applications = _fake_apps
_fake_services.hyprland = _fake_hyprland
_fake_services.audio = _fake_audio
_fake_services.backlight = _fake_backlight
_fake_services.systemd = _fake_systemd
_fake_ignis.services = _fake_services

_fake_base_service = types.ModuleType("ignis.base_service")
_fake_base_service.BaseService = _FakeBaseService
_fake_ignis.base_service = _fake_base_service


# Install — order matters for parents-before-children.
sys.modules.setdefault("gi", _fake_gi)
sys.modules.setdefault("gi.repository", _fake_gi_repo)
sys.modules.setdefault("gi.repository.Gdk", _fake_gi_repo.Gdk)
sys.modules.setdefault("gi.repository.GLib", _fake_gi_repo.GLib)
sys.modules.setdefault("gi.repository.GObject", _fake_gobject)
sys.modules.setdefault("gi.repository.Gtk", _fake_gi_repo.Gtk)
sys.modules.setdefault("gi.repository.GdkPixbuf", _fake_gi_repo.GdkPixbuf)
sys.modules.setdefault("ignis", _fake_ignis)
sys.modules.setdefault("ignis.widgets", _fake_ignis.widgets)
sys.modules.setdefault("ignis.app", _fake_ignis.app)
sys.modules.setdefault("ignis.menu_model", _fake_ignis.menu_model)
sys.modules.setdefault("ignis.services", _fake_services)
sys.modules.setdefault("ignis.services.applications", _fake_apps)
sys.modules.setdefault("ignis.services.hyprland", _fake_hyprland)
sys.modules.setdefault("ignis.services.audio", _fake_audio)
sys.modules.setdefault("ignis.services.backlight", _fake_backlight)
sys.modules.setdefault("ignis.services.systemd", _fake_systemd)
sys.modules.setdefault("ignis.base_service", _fake_base_service)


# ---------------------------------------------------------------------------
# Real-I/O fixtures — every fixture writes a real file in tmp_path.
# Filesystem is never mocked.
# ---------------------------------------------------------------------------

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


@pytest.fixture
def tmp_systemd_config(tmp_path):
    """Create a real systemd.toml with an array-of-tables unit list."""
    config_path = tmp_path / "systemd.toml"
    data = {
        "units": [
            {
                "unit": "waybar.service",
                "description": "Status bar",
                "icon": "preferences-desktop-display",
            },
            {
                "unit": "sshd.service",
                "description": "SSH daemon",
                "bus": "system",
            },
        ]
    }
    config_path.write_text(toml.dumps(data))
    return config_path
