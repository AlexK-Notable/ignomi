"""
Screens - Full-window content trees that swap inside the single launcher.

See `manager.py` for the mechanism and the rationale. Adding a screen:

  1. Write a class with `name`, `title`, `icon` and `create_widget()`.
  2. Register it in `RootPanel.__init__` (`self.screens.register(...)`).

The nav button on the home screen is generated automatically, and the
shortcuts screen documents it automatically if you give it a
`description`. Give its visible container the `panel` CSS class and
click-to-dismiss works too.
"""

from screens.clipboard import ClipboardScreen
from screens.home import HomeScreen
from screens.manager import Screen, ScreenManager
from screens.shortcuts import ShortcutsScreen
from screens.systemd import SystemdScreen

__all__ = [
    "ClipboardScreen",
    "HomeScreen",
    "Screen",
    "ScreenManager",
    "ShortcutsScreen",
    "SystemdScreen",
]
