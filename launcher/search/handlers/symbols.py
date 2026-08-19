"""
Symbols Handler - Emoji and unicode symbol search via elephant.

Usage: type ":" followed by a name, e.g. `:smile`, `:arrow`, `:heart`.
Activating a result copies the character to the clipboard.

Ignis has no emoji support of any kind (a grep for `emoji` across the
whole package returns nothing), so this is provided by elephant's
`symbols` provider rather than reimplemented.

Note on rendering: elephant returns the character itself in the `icon`
field and its name in `text`. A raw character is not a GTK icon name, so
the character goes into the result *title* and `icon` is set to a real
theme icon. Passing the emoji as `widgets.Icon(image=...)` renders
nothing.
"""

import os
import sys

from loguru import logger

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from search.router import ResultItem
from services.elephant import get_elephant_client

PREFIX = ":"


class SymbolsHandler:
    """Emoji / unicode search via elephant's `symbols` provider."""

    name = "symbols"
    priority = 150

    # Optional metadata, read by the shortcuts screen to document itself.
    prefixes = [PREFIX]
    description = "Emoji and unicode symbols — copies to clipboard"
    example = ":smile"

    def __init__(self, max_results: int = 30):
        self.max_results = max_results
        self.client = get_elephant_client()

    def matches(self, query: str) -> bool:
        q = query.strip()
        return q.startswith(PREFIX) and len(q) > len(PREFIX)

    def get_results(self, query: str) -> list[ResultItem]:
        term = query.strip()[len(PREFIX):].strip()
        if not term:
            return []

        items = self.client.query("symbols", term, self.max_results)

        if not items:
            return [ResultItem(
                title=f"No symbols matching '{term}'",
                description=(
                    "Elephant daemon unavailable"
                    if not self.client.is_available()
                    else "Try a different word"
                ),
                icon="face-plain",
                result_type="symbol",
            )]

        return [self._to_result(item) for item in items]

    def _to_result(self, item) -> ResultItem:
        character = item.icon or "?"
        return ResultItem(
            # The character leads, so the list scans visually.
            title=f"{character}   {item.text}",
            description="Copy to clipboard",
            icon="face-smile",
            result_type="symbol",
            on_activate=lambda i=item: self._copy(i),
        )

    def _copy(self, item):
        """Copy the symbol, then close the launcher."""
        ok = self.client.activate("symbols", item.identifier, "run_cmd")
        if not ok:
            logger.warning(f"[symbols] could not copy {item.text!r}")

        from utils.helpers import close_launcher

        close_launcher()
