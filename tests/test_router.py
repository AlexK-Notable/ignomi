"""
Tests for the QueryRouter dispatch logic.

Uses real router and minimal stub handlers (no GTK dependency).
"""

import pytest
from unittest.mock import patch, MagicMock


# Mock Ignis modules
@pytest.fixture(autouse=True)
def _mock_ignis():
    with patch.dict("sys.modules", {
        "ignis": MagicMock(),
        "ignis.services": MagicMock(),
        "ignis.services.applications": MagicMock(),
    }):
        yield


class StubHandler:
    """Minimal handler for testing router dispatch."""

    def __init__(self, name, priority, match_fn=None):
        self._name = name
        self._priority = priority
        self._match_fn = match_fn or (lambda q: True)

    @property
    def name(self):
        return self._name

    @property
    def priority(self):
        return self._priority

    def matches(self, query):
        return self._match_fn(query)

    def get_results(self, query):
        from search.router import ResultItem
        return [ResultItem(title=f"{self._name}: {query}")]


class TestQueryRouter:
    """Test priority-ordered handler dispatch."""

    def test_empty_query_routes_to_app_search(self):
        from search.router import QueryRouter
        router = QueryRouter()
        router.register(StubHandler("app_search", 1000))
        handler_name, results = router.route("")
        assert handler_name == "app_search"

    def test_none_query_routes_to_app_search(self):
        from search.router import QueryRouter
        router = QueryRouter()
        router.register(StubHandler("app_search", 1000))
        handler_name, results = router.route("   ")
        assert handler_name == "app_search"

    def test_first_matching_handler_wins(self):
        from search.router import QueryRouter
        router = QueryRouter()
        router.register(StubHandler("low", 100, lambda q: True))
        router.register(StubHandler("high", 200, lambda q: True))
        handler_name, _ = router.route("test")
        assert handler_name == "low"  # lower priority number = higher priority

    def test_skips_non_matching_handlers(self):
        from search.router import QueryRouter
        router = QueryRouter()
        router.register(StubHandler("nope", 100, lambda q: False))
        router.register(StubHandler("yes", 200, lambda q: True))
        handler_name, _ = router.route("test")
        assert handler_name == "yes"

    def test_no_match_returns_none(self):
        from search.router import QueryRouter
        router = QueryRouter()
        router.register(StubHandler("nope", 100, lambda q: False))
        handler_name, results = router.route("test")
        assert handler_name == "none"
        assert results == []

    def test_handlers_sorted_by_priority(self):
        from search.router import QueryRouter
        router = QueryRouter()
        router.register(StubHandler("c", 300))
        router.register(StubHandler("a", 100))
        router.register(StubHandler("b", 200))
        priorities = [h.priority for h in router._handlers]
        assert priorities == [100, 200, 300]
