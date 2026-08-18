"""
Screens - Full-window content trees that swap inside the single launcher.

See `manager.py` for the mechanism and the rationale. Adding a screen:

  1. Write a class with `name`, `title`, `icon` and `create_widget()`.
  2. Register it in `RootPanel.__init__` (`self.screens.register(...)`).

The nav button on the home screen is generated automatically.
"""

from screens.home import HomeScreen
from screens.manager import Screen, ScreenManager
from screens.systemd import SystemdScreen

__all__ = [
    "HomeScreen",
    "Screen",
    "ScreenManager",
    "SystemdScreen",
]
