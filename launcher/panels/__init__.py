# Ignomi Panels Package
"""
Panel implementations for the three-panel launcher.

Each panel is responsible for its own UI and interaction logic.
"""

from .bookmarks import BookmarksPanel
from .search import SearchPanel
from .frequent import FrequentPanel

__all__ = ["BookmarksPanel", "SearchPanel", "FrequentPanel"]
