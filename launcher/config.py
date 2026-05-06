"""
Ignomi Launcher - Main Ignis Configuration

Entry point for Ignis. Builds a SINGLE Layer Shell window
(`ignomi-launcher`) that hosts every panel — bookmarks (left), search
(center), frequent (right), and an animated blur backdrop. See
project-docs/architecture/2026-04-30-animation-architecture.md for the
full architectural rationale (A1 refactor).

Usage:
  scripts/toggle-launcher.sh          # Toggle the launcher
  ignis open-window ignomi-launcher   # Open for debugging
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

# Add launcher to path dynamically (works from any location/worktree).
# Resolve symlink to get the actual launcher directory.
config_dir = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, config_dir)

# Get Ignis app instance early — needed even if construction below fails so
# we can surface the error in the daemon log rather than dying silently.
app = IgnisApp.get_default()

# Load CSS styling. Apply at "user" priority (800) to override global
# GTK4 CSS (~/.config/gtk-4.0/gtk.css). colors.css should be symlinked
# from Wallust output.
styles_dir = os.path.join(config_dir, "styles")
for css_file in ("colors.css", "main.css"):
    css_path = os.path.join(styles_dir, css_file)
    try:
        app.apply_css(css_path, style_priority="user")
    except Exception as e:
        logger.warning(f"Could not load {css_file} from {css_path}: {e}")

# M9 failure-to-start handling: if any panel fails to construct, log the
# full traceback and surface a minimal placeholder window so the user
# sees SOMETHING (not a silently-broken launcher).
try:
    from panels.root import RootPanel

    root_panel = RootPanel()
    root_window = root_panel.create_window()
    logger.info("Ignomi launcher initialized successfully")
except Exception:
    logger.exception(
        "FATAL: Ignomi panel construction failed. "
        "Launcher will not appear. Check ~/.local/share/ignomi/ignomi.log "
        "for the full traceback."
    )
    # Re-raise so `ignis init` exits non-zero — better than starting a
    # half-broken daemon that silently does nothing on toggle.
    raise
