"""
Ignomi Launcher - Main Ignis Configuration

This file is the entry point for Ignis. It creates all three panels
(bookmarks, search, frequent) and coordinates their display.

Usage:
  scripts/toggle-launcher.sh          # Toggle all three panels
  ignis open-window ignomi-bookmarks  # Open bookmarks panel only
  ignis open-window ignomi-search     # Open search panel only
  ignis open-window ignomi-frequent   # Open frequent panel only
"""

from ignis.app import IgnisApp
import sys
import os

# Add launcher to path dynamically (works from any location/worktree)
# Resolve symlink to get the actual launcher directory
config_dir = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, config_dir)

from panels.bookmarks import BookmarksPanel
from panels.search import SearchPanel
from panels.frequent import FrequentPanel

# Get Ignis app instance
app = IgnisApp.get_default()

# Load CSS styling dynamically from current location
# Note: colors.css should be symlinked from Wallust output
# Use "user" priority (800) to override global GTK4 CSS (~/.config/gtk-4.0/gtk.css)
styles_dir = os.path.join(config_dir, "styles")
try:
    app.apply_css(os.path.join(styles_dir, "colors.css"), style_priority="user")
except Exception as e:
    print(f"Warning: Could not load colors.css: {e}")

try:
    app.apply_css(os.path.join(styles_dir, "main.css"), style_priority="user")
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

# Store panel references on windows for cross-panel communication
bookmarks_window.panel = bookmarks_panel
search_window.panel = search_panel
frequent_window.panel = frequent_panel

print("Ignomi launcher initialized successfully")
print("Press Mod+Space to open launcher")
