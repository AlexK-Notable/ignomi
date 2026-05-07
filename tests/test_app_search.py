"""
Tests for the AppSearchHandler.

Since AppSearchHandler depends heavily on ApplicationsService (GTK),
these tests focus on the tiered scoring algorithm and result conversion
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


def _build_handler(apps, frecency_service=None):
    """Bypass __init__ (avoids GTK construction) and wire instance attrs."""
    handler = AppSearchHandler.__new__(AppSearchHandler)
    handler.apps_service = MagicMock()
    handler.apps_service.apps = apps
    handler.max_results = 30
    handler.fuzzy_threshold = 50
    handler.frecency_service = frecency_service
    return handler


class TestAppSearchHandler:
    """Test app search handler behavior."""

    def test_always_matches(self):
        handler = _build_handler([])
        assert handler.matches("anything") is True
        assert handler.matches("") is True

    def test_empty_query_returns_default_apps(self):
        apps = [_make_app(f"app{i}.desktop", f"App {i}") for i in range(25)]
        handler = _build_handler(apps)

        results = handler.get_results("")
        # Should return up to 20 (the default slice)
        assert len(results) == 20

    def test_results_are_result_items(self):
        apps = [_make_app("firefox.desktop", "Firefox", "Web Browser")]
        handler = _build_handler(apps)

        results = handler.get_results("")
        assert len(results) == 1
        assert isinstance(results[0], ResultItem)
        assert results[0].title == "Firefox"
        assert results[0].result_type == "app"
        assert results[0].app is apps[0]


class TestTieredScoring:
    """
    Validate the tier-based scorer in app_search.py.

    The original WRatio-only scorer ranked RustDesk and GitHub Desktop
    above Vesktop when the user typed "vesk" (all three share the
    substring "esk" but only Vesktop is a true prefix match). The
    tiered scorer must put Vesktop first.
    """

    @pytest.mark.skipif(not HAS_RAPIDFUZZ, reason="rapidfuzz not installed")
    def test_prefix_beats_substring_and_fuzzy(self):
        apps = [
            _make_app("rustdesk.desktop", "RustDesk", "Remote Desktop"),
            _make_app("github-desktop.desktop", "GitHub Desktop", "Git client"),
            _make_app("remmina.desktop", "Remmina Remote Desktop Client", ""),
            _make_app("vesktop.desktop", "Vesktop", "Custom Discord client"),
        ]
        handler = _build_handler(apps)

        results = handler.get_results("vesk")
        assert results, "expected at least one result"
        assert results[0].title == "Vesktop", (
            f"prefix match must win over fuzzy/substring matches; got {[r.title for r in results]}"
        )

    def test_exact_match_beats_prefix_match(self):
        apps = [
            _make_app("code-oss.desktop", "Code - OSS"),
            _make_app("code.desktop", "Code"),
        ]
        handler = _build_handler(apps)

        results = handler.get_results("code")
        assert results[0].title == "Code"
        assert results[1].title == "Code - OSS"

    def test_prefix_beats_word_prefix(self):
        # "fire" is a prefix of "firefox" but only a word-prefix in
        # "Mozilla Firefox" — both should rank above other word-prefix
        # tier matches like "Firewall Tools" via length-penalty tiebreak.
        apps = [
            _make_app("a.desktop", "Mozilla Firefox"),  # token starts with fire
            _make_app("b.desktop", "Firefox"),           # name starts with fire
        ]
        handler = _build_handler(apps)

        results = handler.get_results("fire")
        assert results[0].title == "Firefox", (
            "name-prefix tier must beat word-prefix tier"
        )

    def test_word_prefix_beats_substring(self):
        # "term" matches token "Terminal" in tier 3, and is a substring
        # of "alacritty-terminal" in tier 4. Tier 3 must win.
        apps = [
            _make_app("a.desktop", "alacritty-terminal"),
            _make_app("b.desktop", "GNOME Terminal"),
        ]
        handler = _build_handler(apps)

        results = handler.get_results("term")
        assert results[0].title == "GNOME Terminal"

    def test_shorter_name_wins_within_tier(self):
        apps = [
            _make_app("a.desktop", "Vesktop Beta Edition Long Name"),
            _make_app("b.desktop", "Vesktop"),
        ]
        handler = _build_handler(apps)

        results = handler.get_results("vesk")
        assert results[0].title == "Vesktop"

    def test_no_match_returns_empty(self):
        apps = [_make_app("a.desktop", "Firefox")]
        handler = _build_handler(apps)

        results = handler.get_results("zzzzznoapp")
        assert results == []

    def test_app_with_empty_name_skipped(self):
        apps = [
            _make_app("a.desktop", "Firefox"),
            _make_app("b.desktop", ""),
        ]
        handler = _build_handler(apps)

        results = handler.get_results("fire")
        assert len(results) == 1
        assert results[0].title == "Firefox"


class TestFrecencyBoost:
    """
    Validate that frecency boost tiebreaks within a tier but never
    crosses tier boundaries (i.e. a wildly-popular substring match
    must never beat an unused prefix match).
    """

    def _frecency_stub(self, scores: dict[str, float]):
        stub = MagicMock()
        stub.get_frecency_score = lambda app_id: scores.get(app_id, 0.0)
        return stub

    def test_frecency_breaks_tie_within_tier(self):
        # Both names start with "vim" → same tier. Length penalty makes
        # the longer name ~12 points lower; frecency on the longer name
        # should overcome that.
        apps = [
            _make_app("a.desktop", "Vim Editor"),         # 10 chars, unused
            _make_app("b.desktop", "Vim Tools Plus IDE"), # 18 chars, heavily used
        ]
        stub = self._frecency_stub({"b.desktop": 5000})
        handler = _build_handler(apps, frecency_service=stub)

        results = handler.get_results("vim")
        assert results[0].title == "Vim Tools Plus IDE"

    def test_frecency_does_not_promote_across_tiers(self):
        # Popularity bomb (10000 score → 27 boost, capped at 20) must NOT
        # let a substring-tier app beat a name-prefix-tier app.
        apps = [
            _make_app("popular.desktop", "Notepad - Code"),  # substring tier
            _make_app("rare.desktop", "Code"),               # exact name match
        ]
        stub = self._frecency_stub({"popular.desktop": 1_000_000})
        handler = _build_handler(apps, frecency_service=stub)

        results = handler.get_results("code")
        assert results[0].title == "Code", (
            "frecency boost must never cross tier boundaries"
        )

    def test_frecency_service_none_is_safe(self):
        apps = [_make_app("a.desktop", "Firefox")]
        handler = _build_handler(apps, frecency_service=None)

        results = handler.get_results("fire")
        assert results[0].title == "Firefox"

    def test_frecency_service_exception_is_swallowed(self):
        bad_service = MagicMock()
        bad_service.get_frecency_score.side_effect = RuntimeError("db gone")
        apps = [_make_app("a.desktop", "Firefox")]
        handler = _build_handler(apps, frecency_service=bad_service)

        results = handler.get_results("fire")
        assert results[0].title == "Firefox"
