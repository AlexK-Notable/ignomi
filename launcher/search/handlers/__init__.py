"""
Search handlers - Pluggable query processors.

Each handler checks if it can handle a query and returns typed results.
"""

from .app_search import AppSearchHandler
from .calculator import CalculatorHandler
from .controls import SystemControlsHandler
from .web_search import WebSearchHandler
from .commands import CustomCommandsHandler

__all__ = [
    "AppSearchHandler",
    "CalculatorHandler",
    "SystemControlsHandler",
    "WebSearchHandler",
    "CustomCommandsHandler",
]
