# Ignomi Panels Package
"""
Panel implementations for the launcher.

Since the A1 single-window refactor (2026-05), all panels live inside a
single Layer Shell window owned by RootPanel. The individual panel
classes return widget trees (via `create_widget()`) rather than Window
instances; RootPanel composes them into the single window.
"""

from .bookmarks import BookmarksPanel
from .frequent import FrequentPanel
from .root import RootPanel
from .search import SearchPanel

__all__ = ["BookmarksPanel", "FrequentPanel", "RootPanel", "SearchPanel"]
