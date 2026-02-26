"""
Tests for the AppSearchHandler.

Since AppSearchHandler depends heavily on ApplicationsService (GTK),
these tests focus on the fuzzy matching logic and result conversion
using mock app objects.
"""

import sys
import types
from unittest.mock import MagicMock

import pytest

# Patch GTK/Ignis for headless testing (including ignis.widgets for controls.py)
_saved_modules = {}
_modules_to_fake = [
    "gi", "gi.repository",
    "ignis", "ignis.widgets",
    "ignis.services", "ignis.services.applications",
    "ignis.services.audio", "ignis.services.backlight",
]
for _mod in _modules_to_fake:
    if _mod in sys.modules:
        _saved_modules[_mod] = sys.modules[_mod]

_fake_gi = types.ModuleType("gi")
_fake_gi_repo = types.ModuleType("gi.repository")
_fake_gi.repository = _fake_gi_repo
_fake_ignis = types.ModuleType("ignis")
_fake_ignis.widgets = MagicMock()
_fake_services = types.ModuleType("ignis.services")
_fake_apps = types.ModuleType("ignis.services.applications")
_fake_services.audio = MagicMock()
_fake_services.backlight = MagicMock()

# Mock ApplicationsService.get_default() to return a mock with apps list
_mock_apps_service = MagicMock()
_mock_apps_service.apps = []
_fake_apps.ApplicationsService = MagicMock()
_fake_apps.ApplicationsService.get_default.return_value = _mock_apps_service

_fake_ignis.services = _fake_services
_fake_services.applications = _fake_apps

sys.modules["gi"] = _fake_gi
sys.modules["gi.repository"] = _fake_gi_repo
sys.modules["ignis"] = _fake_ignis
sys.modules["ignis.widgets"] = _fake_ignis.widgets
sys.modules["ignis.services"] = _fake_services
sys.modules["ignis.services.applications"] = _fake_apps
sys.modules["ignis.services.audio"] = _fake_services.audio
sys.modules["ignis.services.backlight"] = _fake_services.backlight

from search.handlers.app_search import AppSearchHandler, HAS_RAPIDFUZZ
from search.router import ResultItem

# Restore modules
for _mod in _modules_to_fake:
    if _mod in _saved_modules:
        sys.modules[_mod] = _saved_modules[_mod]
    elif _mod in sys.modules:
        del sys.modules[_mod]


def _make_app(app_id, name, description=""):
    """Create a mock application object."""
    app = MagicMock()
    app.id = app_id
    app.name = name
    app.description = description
    app.icon = "application-x-executable"
    return app


class TestAppSearchHandler:
    """Test app search handler behavior."""

    def test_always_matches(self):
        handler = AppSearchHandler.__new__(AppSearchHandler)
        handler.apps_service = MagicMock()
        handler.max_results = 30
        handler.fuzzy_threshold = 50
        assert handler.matches("anything") is True
        assert handler.matches("") is True

    def test_empty_query_returns_default_apps(self):
        apps = [_make_app(f"app{i}.desktop", f"App {i}") for i in range(25)]
        handler = AppSearchHandler.__new__(AppSearchHandler)
        handler.apps_service = MagicMock()
        handler.apps_service.apps = apps
        handler.max_results = 30
        handler.fuzzy_threshold = 50

        results = handler.get_results("")
        # Should return up to 20 (the default slice)
        assert len(results) == 20

    def test_results_are_result_items(self):
        apps = [_make_app("firefox.desktop", "Firefox", "Web Browser")]
        handler = AppSearchHandler.__new__(AppSearchHandler)
        handler.apps_service = MagicMock()
        handler.apps_service.apps = apps
        handler.max_results = 30
        handler.fuzzy_threshold = 50

        results = handler.get_results("")
        assert len(results) == 1
        assert isinstance(results[0], ResultItem)
        assert results[0].title == "Firefox"
        assert results[0].result_type == "app"
        assert results[0].app is apps[0]

    @pytest.mark.skipif(not HAS_RAPIDFUZZ, reason="rapidfuzz not installed")
    def test_fuzzy_search_finds_close_match(self):
        apps = [
            _make_app("firefox.desktop", "Firefox", "Web Browser"),
            _make_app("code.desktop", "Visual Studio Code", "Code Editor"),
            _make_app("nautilus.desktop", "Files", "File Manager"),
        ]
        handler = AppSearchHandler.__new__(AppSearchHandler)
        handler.apps_service = MagicMock()
        handler.apps_service.apps = apps
        handler.max_results = 30
        handler.fuzzy_threshold = 50

        results = handler._fuzzy_search("firefx", apps)  # Typo
        assert len(results) >= 1
        assert results[0].title == "Firefox"
