"""
Search handlers - Pluggable query processors.

Each handler checks if it can handle a query and returns typed results.

Handlers may also expose optional self-documentation metadata —
`prefixes`, `description`, `example` — which the shortcuts screen reads
to build its cheat sheet. See screens/shortcuts.py.
"""

from .app_search import AppSearchHandler
from .calculator import CalculatorHandler
from .commands import CustomCommandsHandler
from .controls import SystemControlsHandler
from .files import FilesHandler
from .symbols import SymbolsHandler
from .web_search import WebSearchHandler

__all__ = [
    "AppSearchHandler",
    "CalculatorHandler",
    "FilesHandler",
    "SymbolsHandler",
    "SystemControlsHandler",
    "WebSearchHandler",
    "CustomCommandsHandler",
]
