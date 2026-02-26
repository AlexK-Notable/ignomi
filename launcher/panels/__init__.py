# Ignomi Panels Package
"""
Panel implementations for the three-panel launcher.

Each panel is responsible for its own UI and interaction logic.
"""

from .bookmarks import BookmarksPanel
from .frequent import FrequentPanel
from .search import SearchPanel

__all__ = ["BookmarksPanel", "SearchPanel", "FrequentPanel"]
