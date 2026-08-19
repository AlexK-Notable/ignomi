"""
Query Router - Dispatches search queries to priority-ordered handlers.

Each handler declares a priority (lower = higher priority) and a matches()
method. The router finds the first matching handler and returns its results.
App search is always the fallback (highest priority number).
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol


@dataclass
class ResultItem:
    """A single search result from any handler."""
    title: str
    description: str = ""
    icon: str = "image-missing"
    result_type: str = "app"  # app, calculator, control, web, command
    on_activate: Callable | None = None
    widget_builder: Callable | None = None
    app: object = None  # Application object for app results


class SearchHandler(Protocol):
    """Structural type for search handlers. No inheritance required."""
    name: str
    priority: int

    def matches(self, query: str) -> bool: ...
    def get_results(self, query: str) -> list[ResultItem]: ...


class QueryRouter:
    """Routes queries to the appropriate handler based on priority."""

    def __init__(self):
        self._handlers: list[SearchHandler] = []

    def register(self, handler: SearchHandler) -> None:
        """Register a handler and re-sort by priority."""
        self._handlers.append(handler)
        self._handlers.sort(key=lambda h: h.priority)

    @property
    def handlers(self) -> list[SearchHandler]:
        """Registered handlers, in priority order (lowest number first).

        Exposed so the shortcuts screen can document what the search bar
        accepts by reading the live registry rather than a hand-written
        list that would silently go stale. Returns a copy — callers must
        not reorder the router's dispatch.
        """
        return list(self._handlers)

    def route(self, query: str) -> tuple[str, list[ResultItem]]:
        """
        Find the first matching handler and return its results.

        Args:
            query: The search query string

        Returns:
            Tuple of (handler_name, results_list).
            Returns ("none", []) if no handler matches.
        """
        if not query or not query.strip():
            # Empty query - let app search show defaults
            for handler in self._handlers:
                if handler.name == "app_search":
                    return handler.name, handler.get_results("")
            return "none", []

        for handler in self._handlers:
            if handler.matches(query):
                return handler.name, handler.get_results(query)

        return "none", []
