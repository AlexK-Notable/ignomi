"""
Ignomi Launcher - Main Ignis Configuration

This file is the entry point for Ignis. It creates all three panels
and coordinates their display.

Usage:
  ignis open-window ignomi
"""

from ignis.app import IgnisApp
import sys

# Add launcher to path
sys.path.insert(0, '/home/komi/repos/ignomi/launcher')

from panels.bookmarks import BookmarksPanel
from panels.search import SearchPanel
from panels.frequent import FrequentPanel

# Get Ignis app instance
app = IgnisApp.get_default()

# Load CSS styling
# Note: colors.css should be symlinked from Wallust output
try:
    app.apply_css("/home/komi/repos/ignomi/launcher/styles/colors.css")
except Exception as e:
    print(f"Warning: Could not load colors.css: {e}")

try:
    app.apply_css("/home/komi/repos/ignomi/launcher/styles/main.css")
except Exception as e:
    print(f"Warning: Could not load main.css: {e}")

# Create panels
bookmarks_panel = BookmarksPanel()
search_panel = SearchPanel()
frequent_panel = FrequentPanel()

# Create windows
bookmarks_window = bookmarks_panel.create_window()
search_window = search_panel.create_window()
frequent_window = frequent_panel.create_window()

print("Ignomi launcher initialized successfully")
print("Press Mod+Space to open launcher")
