"""
Query Router - Dispatches search queries to priority-ordered handlers.

Each handler declares a priority (lower = higher priority) and a matches()
method. The router finds the first matching handler and returns its results.
App search is always the fallback (highest priority number).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Callable


@dataclass
class ResultItem:
    """A single search result from any handler."""
    title: str
    description: str = ""
    icon: str = "image-missing"
    result_type: str = "app"  # app, calculator, control, web, command
    on_activate: Optional[Callable] = None
    widget_builder: Optional[Callable] = None
    app: object = None  # Application object for app results


class SearchHandler(ABC):
    """Base class for all search handlers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Handler identifier."""
        ...

    @property
    @abstractmethod
    def priority(self) -> int:
        """Lower number = checked first. App search should be ~1000."""
        ...

    @abstractmethod
    def matches(self, query: str) -> bool:
        """Return True if this handler should process the query."""
        ...

    @abstractmethod
    def get_results(self, query: str) -> list[ResultItem]:
        """Return results for the query."""
        ...


class QueryRouter:
    """Routes queries to the appropriate handler based on priority."""

    def __init__(self):
        self._handlers: list[SearchHandler] = []

    def register(self, handler: SearchHandler) -> None:
        """Register a handler and re-sort by priority."""
        self._handlers.append(handler)
        self._handlers.sort(key=lambda h: h.priority)

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
