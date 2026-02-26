"""
Calculator Handler - Inline math evaluation in search.

Triggers on "=" prefix. Uses simpleeval for safe expression evaluation
(no access to builtins, filesystem, or imports).

Install: pipx inject ignis simpleeval
"""

import math
import subprocess

from loguru import logger
from search.router import ResultItem

try:
    from simpleeval import InvalidExpression, simple_eval
    HAS_SIMPLEEVAL = True
except ImportError:
    HAS_SIMPLEEVAL = False


class CalculatorHandler:
    """Evaluate math expressions prefixed with '='."""

    name = "calculator"
    priority = 100

    def matches(self, query: str) -> bool:
        if not HAS_SIMPLEEVAL:
            return False
        return query.strip().startswith("=")

    def get_results(self, query: str) -> list[ResultItem]:
        expr = query.strip().lstrip("=").strip()
        if not expr:
            return [ResultItem(
                title="Type an expression",
                description="e.g. = 2 + 2, = sqrt(16), = pi * 2",
                icon="accessories-calculator",
                result_type="calculator",
            )]

        try:
            result = simple_eval(
                expr,
                functions={
                    "sqrt": math.sqrt,
                    "abs": abs,
                    "round": round,
                    "sin": math.sin,
                    "cos": math.cos,
                    "tan": math.tan,
                    "log": math.log,
                    "log10": math.log10,
                    "pow": pow,
                    "min": min,
                    "max": max,
                },
                names={
                    "pi": math.pi,
                    "e": math.e,
                },
            )

            # Format result nicely
            if isinstance(result, float) and result == int(result):
                display = str(int(result))
            else:
                display = str(result)

            return [ResultItem(
                title=display,
                description=f"= {expr}",
                icon="accessories-calculator",
                result_type="calculator",
                on_activate=lambda r=display: self._copy_to_clipboard(r),
            )]

        except InvalidExpression:
            return [ResultItem(
                title="Invalid expression",
                description=f"Could not evaluate: {expr[:60]}",
                icon="dialog-error",
                result_type="calculator",
            )]
        except (TypeError, ValueError, ZeroDivisionError, OverflowError) as e:
            return [ResultItem(
                title="Math error",
                description=str(e)[:80],
                icon="dialog-error",
                result_type="calculator",
            )]
        except Exception as e:
            logger.warning(f"Unexpected calculator error for '{expr}': {e}")
            return [ResultItem(
                title="Error",
                description=str(e)[:80],
                icon="dialog-error",
                result_type="calculator",
            )]

    def _copy_to_clipboard(self, text: str):
        """Copy result to clipboard using wl-copy."""
        try:
            subprocess.Popen(
                ["wl-copy", text],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            logger.debug("wl-copy not found, cannot copy to clipboard")

        from utils.helpers import close_launcher
        close_launcher()
