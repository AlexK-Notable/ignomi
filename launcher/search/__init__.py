"""
Search package - Query routing and handler framework.

Provides a pluggable search system where queries are dispatched to
priority-ordered handlers (app search, calculator, web search, etc.).
"""

from .router import QueryRouter, SearchHandler, ResultItem

__all__ = ["QueryRouter", "SearchHandler", "ResultItem"]
