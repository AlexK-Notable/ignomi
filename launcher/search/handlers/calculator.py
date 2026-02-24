"""
Calculator Handler - Inline math evaluation in search.

Triggers on "=" prefix. Uses simpleeval for safe expression evaluation
(no access to builtins, filesystem, or imports).

Install: pipx inject ignis simpleeval
"""

import subprocess
from search.router import SearchHandler, ResultItem

try:
    from simpleeval import simple_eval, InvalidExpression
    HAS_SIMPLEEVAL = True
except ImportError:
    HAS_SIMPLEEVAL = False


class CalculatorHandler(SearchHandler):
    """Evaluate math expressions prefixed with '='."""

    @property
    def name(self) -> str:
        return "calculator"

    @property
    def priority(self) -> int:
        return 100

    def matches(self, query: str) -> bool:
        if not HAS_SIMPLEEVAL:
            return False
        return query.strip().startswith("=")

    def get_results(self, query: str) -> list[ResultItem]:
        expr = query.strip().lstrip("=").strip()
        if not expr:
            return [ResultItem(
                title="Type an expression",
                description="e.g. = 2 + 2, = sqrt(16), = 3 * (4 + 5)",
                icon="accessories-calculator",
                result_type="calculator",
            )]

        try:
            import math
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
                    "pi": math.pi,
                    "e": math.e,
                    "pow": pow,
                    "min": min,
                    "max": max,
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

        except (InvalidExpression, Exception) as e:
            return [ResultItem(
                title="Invalid expression",
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
            pass

        from utils.helpers import close_launcher
        close_launcher()
