"""
Tests for the AppSearchHandler.

Since AppSearchHandler depends heavily on ApplicationsService (GTK),
these tests focus on the fuzzy matching logic and result conversion
using mock app objects. Ignis/GTK module mocks are installed by
conftest.py at collection time.
"""

from unittest.mock import MagicMock

import pytest

from search.handlers.app_search import HAS_RAPIDFUZZ, AppSearchHandler
from search.router import ResultItem


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
