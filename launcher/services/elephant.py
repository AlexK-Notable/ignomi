"""
Elephant client - talks to the `elephant` data-provider daemon.

Elephant (github.com/abenz1267/elephant) is Walker's backend daemon. It
already runs on this machine and ships providers Ignis has nothing for:
clipboard history, file search, and emoji/symbol lookup. Rather than
reimplement those, Ignomi queries elephant.

Transport
---------
The `elephant` CLI is used, not the raw unix socket. `elephant query`
speaks a documented, stable interface and returns JSON; the socket wire
format is undocumented. `ignis.utils.socket` (`send_socket`) is
available if this ever needs to get faster, but see the latency numbers
below — it does not.

Protocol (verified empirically against elephant 2.22.0)
------------------------------------------------------
Query — semicolon-separated, NOT flags::

    elephant query --json "<providers>;<query>;<limit>[;exactsearch]"

`providers` may be comma-separated. Output is **NDJSON** — one JSON
object per line, not a JSON array — shaped::

    {"query": "...", "item": {...}, "qid": 1}

Activate — five semicolon-separated fields, the last two empty::

    elephant activate "<provider>;<identifier>;<action>;;"

Fewer than five fields makes the CLI panic with an index error rather
than print a usage message, which is how the arity was discovered.

Known actions per provider:

===============  ====================================================
provider         actions
===============  ====================================================
symbols          run_cmd
clipboard        copy, edit, pin, remove
files            open, opendir, copyfile, copypath
===============  ====================================================

Latency (measured on this machine, median of 5)
-----------------------------------------------
===============  ==========
query            median
===============  ==========
clipboard         6.5 ms
symbols          10.5 ms
files            66.2 ms
===============  ==========

The search router is synchronous, so these block the GTK main thread.
That is why the file provider sits behind an explicit `f:` prefix:
ordinary typing never reaches elephant at all, and the 66 ms is only
spent when the user has actually asked for a file search.

Failure policy
--------------
The daemon may not be running — it is not a systemd unit on this box, it
is a detached process (PPID 1). Every method degrades to empty/False and
logs; nothing here raises into the UI. `is_available()` is a cheap
socket-existence check handlers can gate on so a missing daemon shows an
empty result instead of a stall.
"""

import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from loguru import logger

DEFAULT_TIMEOUT = 3.0
DEFAULT_LIMIT = 20


def _socket_path() -> Path:
    """Where the elephant daemon's unix socket lives."""
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    return Path(runtime_dir) / "elephant" / "elephant.sock"


@dataclass
class ElephantItem:
    """One result row from an elephant provider."""

    identifier: str
    text: str
    provider: str
    subtext: str = ""
    icon: str = ""
    score: int = 0
    preview: str = ""
    preview_type: str = ""
    actions: list[str] = field(default_factory=list)

    @classmethod
    def from_payload(cls, payload: dict) -> "ElephantItem | None":
        """Build from one decoded NDJSON line's `item` object.

        Returns None for a payload without the fields we need, rather
        than raising — a single malformed row must not empty the list.
        """
        item = payload.get("item")
        if not isinstance(item, dict):
            return None

        identifier = item.get("identifier")
        if not identifier:
            return None

        return cls(
            identifier=str(identifier),
            text=item.get("text", ""),
            provider=item.get("provider", ""),
            subtext=item.get("subtext", ""),
            icon=item.get("icon", ""),
            score=item.get("score", 0) or 0,
            preview=item.get("preview", ""),
            preview_type=item.get("preview_type", ""),
            actions=list(item.get("actions") or []),
        )


class ElephantClient:
    """Thin, failure-tolerant wrapper around the `elephant` CLI."""

    def __init__(self, timeout: float = DEFAULT_TIMEOUT):
        self.timeout = timeout

    # --- Availability -------------------------------------------------------

    def is_available(self) -> bool:
        """Is the elephant daemon reachable?

        Checks for the socket rather than shelling out — this is called
        on the UI path and must be free. A stale socket file is possible
        in principle (a crashed daemon), in which case `query()` fails
        cleanly and returns an empty list.
        """
        try:
            return _socket_path().is_socket()
        except OSError:
            return False

    # --- Query --------------------------------------------------------------

    def query(
        self,
        providers: str,
        text: str = "",
        limit: int = DEFAULT_LIMIT,
    ) -> list[ElephantItem]:
        """Run a query against one or more providers.

        Args:
            providers: provider name, or comma-separated names.
            text: the search text. May be empty (clipboard uses this to
                mean "everything", ordered by recency).
            limit: maximum rows.

        Returns:
            Parsed items, best-first as elephant ordered them. Empty on
            any failure — daemon down, timeout, malformed output.
        """
        if not self.is_available():
            logger.debug("[elephant] daemon unavailable; returning no results")
            return []

        content = f"{providers};{text};{limit}"

        try:
            proc = subprocess.run(
                ["elephant", "query", "--json", content],
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
        except subprocess.TimeoutExpired:
            logger.warning(f"[elephant] query timed out after {self.timeout}s: {content}")
            return []
        except FileNotFoundError:
            logger.warning("[elephant] the `elephant` binary is not on PATH")
            return []
        except Exception:
            logger.exception(f"[elephant] query failed: {content}")
            return []

        if proc.returncode != 0:
            logger.warning(
                f"[elephant] query exited {proc.returncode}: "
                f"{(proc.stderr or '').strip()[:200]}"
            )
            return []

        return self._parse_ndjson(proc.stdout)

    @staticmethod
    def _parse_ndjson(stdout: str) -> list[ElephantItem]:
        """Parse elephant's newline-delimited JSON output.

        Each line is decoded independently so one bad line costs one
        row, not the whole result set.
        """
        items = []
        for line in (stdout or "").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                logger.debug(f"[elephant] skipping non-JSON line: {line[:120]}")
                continue

            item = ElephantItem.from_payload(payload)
            if item is not None:
                items.append(item)

        return items

    # --- Activate -----------------------------------------------------------

    def activate(self, provider: str, identifier: str, action: str) -> bool:
        """Run an action on an item (copy it, open it, pin it...).

        Args:
            provider: e.g. "clipboard".
            identifier: the item's `identifier` from `query()`.
            action: one of the item's advertised `actions`.

        Returns:
            True if elephant accepted the activation.
        """
        if not self.is_available():
            logger.warning(f"[elephant] cannot {action}: daemon unavailable")
            return False

        # Five fields. The CLI indexes positionally and panics on fewer.
        content = f"{provider};{identifier};{action};;"

        try:
            proc = subprocess.run(
                ["elephant", "activate", content],
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
        except subprocess.TimeoutExpired:
            logger.warning(f"[elephant] activate timed out: {content}")
            return False
        except FileNotFoundError:
            logger.warning("[elephant] the `elephant` binary is not on PATH")
            return False
        except Exception:
            logger.exception(f"[elephant] activate failed: {content}")
            return False

        if proc.returncode != 0:
            logger.warning(
                f"[elephant] activate exited {proc.returncode}: "
                f"{(proc.stderr or '').strip()[:200]}"
            )
            return False

        logger.debug(f"[elephant] {action} {provider}/{identifier}")
        return True


# -- Singleton --

_elephant_client_instance = None


def get_elephant_client() -> ElephantClient:
    """
    Get the singleton ElephantClient instance.

    Returns:
        ElephantClient: The global instance
    """
    global _elephant_client_instance
    if _elephant_client_instance is None:
        _elephant_client_instance = ElephantClient()
    return _elephant_client_instance
