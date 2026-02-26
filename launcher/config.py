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

import os
import sys
from pathlib import Path

from ignis.app import IgnisApp
from loguru import logger

# Configure logging: file + stderr
logger.remove()  # Remove default stderr handler
logger.add(sys.stderr, level="WARNING")
logger.add(
    Path.home() / ".local" / "share" / "ignomi" / "ignomi.log",
    rotation="1 MB",
    retention=3,
    level="DEBUG",
)

# Add launcher to path dynamically (works from any location/worktree)
# Resolve symlink to get the actual launcher directory
config_dir = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, config_dir)

from panels.backdrop import create_backdrop_window
from panels.bookmarks import BookmarksPanel
from panels.frequent import FrequentPanel
from panels.search import SearchPanel

# Get Ignis app instance
app = IgnisApp.get_default()

# Load CSS styling dynamically from current location
# Note: colors.css should be symlinked from Wallust output
# Use "user" priority (800) to override global GTK4 CSS (~/.config/gtk-4.0/gtk.css)
styles_dir = os.path.join(config_dir, "styles")
try:
    app.apply_css(os.path.join(styles_dir, "colors.css"), style_priority="user")
except Exception as e:
    logger.warning(f"Could not load colors.css: {e}")

try:
    app.apply_css(os.path.join(styles_dir, "main.css"), style_priority="user")
except Exception as e:
    logger.warning(f"Could not load main.css: {e}")

# Create backdrop (full-screen blur overlay)
backdrop_window = create_backdrop_window()

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

logger.info("Ignomi launcher initialized successfully")
