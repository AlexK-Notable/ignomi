"""
Files Handler - File and folder search via elephant.

Usage: type "f:" followed by a name, e.g. `f:cargo.toml`, `f:report`.
Activating a result opens the file with its default application.

Ignis has file *reading* helpers and GTK file *dialog* widgets, but no
search or index, so this comes from elephant's `files` provider (which
is `fd`-backed).

Why this is behind a prefix
---------------------------
A file query measured ~66 ms on this machine, against ~7-10 ms for the
clipboard and symbol providers, because it walks the filesystem. The
search router is synchronous, so that time blocks the GTK main thread.
Putting file search behind an explicit `f:` prefix means ordinary typing
never pays it — the cost is only incurred once the user has actually
asked to search files, where a brief pause reads as "searching" rather
than "stuttering".
"""

import os
import sys

from loguru import logger

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from search.router import ResultItem
from services.elephant import get_elephant_client

PREFIX = "f:"


class FilesHandler:
    """File search via elephant's `files` provider."""

    name = "files"
    priority = 250

    # Optional metadata, read by the shortcuts screen to document itself.
    prefixes = [PREFIX]
    description = "Search files and folders — opens with the default app"
    example = "f:cargo.toml"

    def __init__(self, max_results: int = 25):
        self.max_results = max_results
        self.client = get_elephant_client()

    def matches(self, query: str) -> bool:
        q = query.strip()
        return q.startswith(PREFIX) and len(q) > len(PREFIX)

    def get_results(self, query: str) -> list[ResultItem]:
        term = query.strip()[len(PREFIX):].strip()
        if not term:
            return []

        items = self.client.query("files", term, self.max_results)

        if not items:
            return [ResultItem(
                title=f"No files matching '{term}'",
                description=(
                    "Elephant daemon unavailable"
                    if not self.client.is_available()
                    else "Try a different name"
                ),
                icon="folder",
                result_type="file",
            )]

        return [self._to_result(item) for item in items]

    def _to_result(self, item) -> ResultItem:
        path = item.text or ""
        name = os.path.basename(path.rstrip("/")) or path
        parent = os.path.dirname(path)

        return ResultItem(
            title=name,
            description=parent or path,
            icon="folder" if item.preview_type == "dir" else "text-x-generic",
            result_type="file",
            on_activate=lambda i=item: self._open(i),
        )

    def _open(self, item):
        """Open the file, then close the launcher."""
        ok = self.client.activate("files", item.identifier, "open")
        if not ok:
            logger.warning(f"[files] could not open {item.text!r}")

        from utils.helpers import close_launcher

        close_launcher()
