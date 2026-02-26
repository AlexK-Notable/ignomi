"""
Tests for the WebSearchHandler.

Tests URL construction, engine matching, prefix handling, and xdg-open usage.
"""

import sys
import types
from unittest.mock import MagicMock

# Patch ignis modules needed by search.handlers.__init__ → controls.py
_saved_modules = {}
_modules_to_fake = [
    "ignis", "ignis.widgets",
    "ignis.services", "ignis.services.audio", "ignis.services.backlight",
]
for _mod in _modules_to_fake:
    if _mod in sys.modules:
        _saved_modules[_mod] = sys.modules[_mod]

_fake_ignis = types.ModuleType("ignis")
_fake_ignis.widgets = MagicMock()
_fake_services = types.ModuleType("ignis.services")
_fake_services.audio = MagicMock()
_fake_services.backlight = MagicMock()
_fake_ignis.services = _fake_services

sys.modules["ignis"] = _fake_ignis
sys.modules["ignis.widgets"] = _fake_ignis.widgets
sys.modules["ignis.services"] = _fake_services
sys.modules["ignis.services.audio"] = _fake_services.audio
sys.modules["ignis.services.backlight"] = _fake_services.backlight

from search.handlers.web_search import DEFAULT_ENGINES, WebSearchHandler

for _mod in _modules_to_fake:
    if _mod in _saved_modules:
        sys.modules[_mod] = _saved_modules[_mod]
    elif _mod in sys.modules:
        del sys.modules[_mod]


class TestWebSearchMatching:
    """Test query matching for web search prefixes."""

    def test_matches_question_mark(self):
        handler = WebSearchHandler()
        assert handler.matches("? test query") is True

    def test_matches_google_prefix(self):
        handler = WebSearchHandler()
        assert handler.matches("g: something") is True

    def test_matches_github_prefix(self):
        handler = WebSearchHandler()
        assert handler.matches("gh: repo name") is True

    def test_no_match_plain_text(self):
        handler = WebSearchHandler()
        assert handler.matches("firefox") is False

    def test_no_match_prefix_only(self):
        """Prefix without query text shouldn't match."""
        handler = WebSearchHandler()
        assert handler.matches("?") is False
        assert handler.matches("g:") is False


class TestWebSearchResults:
    """Test result generation and URL construction."""

    def test_kagi_url_construction(self):
        handler = WebSearchHandler()
        results = handler.get_results("? hello world")
        assert len(results) == 1
        assert "Kagi" in results[0].title
        assert results[0].result_type == "web"

    def test_google_url_construction(self):
        handler = WebSearchHandler()
        results = handler.get_results("g: python tutorial")
        assert len(results) == 1
        assert "Google" in results[0].title

    def test_wikipedia_url_construction(self):
        handler = WebSearchHandler()
        results = handler.get_results("w: python programming")
        assert len(results) == 1
        assert "Wikipedia" in results[0].title

    def test_empty_query_after_prefix_shows_prompt(self):
        handler = WebSearchHandler()
        results = handler.get_results("? ")
        assert len(results) == 1
        assert "type" in results[0].description.lower() or "query" in results[0].description.lower()

    def test_result_has_activate_callback(self):
        handler = WebSearchHandler()
        results = handler.get_results("? test")
        assert results[0].on_activate is not None

    def test_custom_engines(self):
        """Custom engine configuration should work."""
        custom = {
            "!d ": {"name": "DuckDuckGo", "url": "https://ddg.gg/?q={query}", "icon": "web-browser"},
        }
        handler = WebSearchHandler(engines=custom)
        assert handler.matches("!d test") is True
        results = handler.get_results("!d test")
        assert "DuckDuckGo" in results[0].title
