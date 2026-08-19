"""
Web Search Handler - Open web searches in the default browser.

Triggers on prefix patterns (defaults shown):
  ? query     → Kagi (default search engine)
  g: query    → Google
  w: query    → Wikipedia
  gh: query   → GitHub
  yt: query   → YouTube

Customization
-------------
The set of search engines is supplied at construction time via the
``engines=`` keyword argument:

    handler = WebSearchHandler(engines={
        "?": {"name": "DuckDuckGo",
              "url": "https://duckduckgo.com/?q={query}",
              "icon": "web-browser"},
    })

If ``engines`` is omitted, ``DEFAULT_ENGINES`` (defined below) is used.

``SearchPanel.__init__`` reads the ``[web_search.engines]`` section of
``data/settings.toml`` and passes the parsed mapping into the
constructor. The TOML schema uses inline tables keyed by prefix:

    [web_search.engines]
    "?"  = { name = "Kagi", url = "https://kagi.com/search?q={query}", icon = "web-browser" }

If the section is absent or empty, ``DEFAULT_ENGINES`` is used. Defining
even one entry REPLACES the defaults entirely — re-add any engines you
want to keep.

Each engine entry is a dict with keys:
  - ``name`` (str): Display name shown in the result row
  - ``url`` (str): URL template containing ``{query}`` placeholder
  - ``icon`` (str, optional): GTK icon name (defaults to ``web-browser``)
"""

import subprocess
import urllib.parse

from loguru import logger
from search.router import ResultItem

# Default search engine URLs (can be overridden in settings.toml)
DEFAULT_ENGINES = {
    "?": {"name": "Kagi", "url": "https://kagi.com/search?q={query}", "icon": "web-browser"},
    "g:": {"name": "Google", "url": "https://www.google.com/search?q={query}", "icon": "web-browser"},
    "w:": {"name": "Wikipedia", "url": "https://en.wikipedia.org/w/index.php?search={query}", "icon": "accessories-dictionary"},
    "gh:": {"name": "GitHub", "url": "https://github.com/search?q={query}", "icon": "web-browser"},
    "yt:": {"name": "YouTube", "url": "https://www.youtube.com/results?search_query={query}", "icon": "applications-multimedia"},
}


class WebSearchHandler:
    """Open web search queries in browser."""

    name = "web_search"
    priority = 200
    _ALLOWED_URL_SCHEMES = ("http://", "https://")
    _REQUIRED_KEYS = frozenset(("name", "url"))

    # Optional metadata, read by the shortcuts screen to document itself.
    # `prefixes` is set per-instance below, since the engine set is
    # user-configurable via settings.toml.
    description = "Search the web — one prefix per configured engine"
    example = "?wayland layer shell"

    def __init__(self, engines: dict = None):
        self.engines = self._validate_engines(engines) if engines else DEFAULT_ENGINES
        self.prefixes = list(self.engines.keys())

    @classmethod
    def _validate_engines(cls, engines: dict) -> dict:
        """
        Validate user-supplied engine config; skip-with-warning on bad entries.

        Rejected (skipped, logger.warning):
          - Empty-string prefix (would shadow every non-empty query).
          - Entry not a dict.
          - Entry missing 'name' or 'url'.
          - URL not starting with http:// or https:// (defence-in-depth
            against file://, vscode://, javascript:, etc.).

        If all entries are rejected, falls back to DEFAULT_ENGINES rather
        than registering a handler that matches nothing useful.
        """
        valid: dict = {}
        for prefix, engine in engines.items():
            if prefix == "":
                logger.warning("WebSearchHandler: rejecting empty-string prefix (would shadow other handlers)")
                continue
            if not isinstance(engine, dict):
                logger.warning(f"WebSearchHandler: rejecting prefix {prefix!r} — entry is not a dict")
                continue
            missing = cls._REQUIRED_KEYS - engine.keys()
            if missing:
                logger.warning(f"WebSearchHandler: rejecting prefix {prefix!r} — missing keys {sorted(missing)}")
                continue
            url = engine["url"]
            if not isinstance(url, str) or not url.startswith(cls._ALLOWED_URL_SCHEMES):
                logger.warning(f"WebSearchHandler: rejecting prefix {prefix!r} — url must be http(s):// (got {url!r:.40})")
                continue
            valid[prefix] = engine
        return valid or DEFAULT_ENGINES

    def matches(self, query: str) -> bool:
        q = query.strip()
        for prefix in self.engines:
            if q.startswith(prefix) and len(q) > len(prefix):
                return True
        return False

    def get_results(self, query: str) -> list[ResultItem]:
        q = query.strip()

        for prefix, engine in self.engines.items():
            if q.startswith(prefix):
                search_term = q[len(prefix):].strip()
                if not search_term:
                    return [ResultItem(
                        title=f"Search {engine['name']}...",
                        description=f"Type a query after '{prefix}'",
                        icon=engine.get("icon", "web-browser"),
                        result_type="web",
                    )]

                # Use str.replace (not str.format) to eliminate format-spec
                # interpretation (CWE-134 defense). Schema only documents {query}.
                url = engine["url"].replace(
                    "{query}", urllib.parse.quote_plus(search_term)
                )

                return [
                    ResultItem(
                        title=f"Search {engine['name']}: {search_term}",
                        description=engine["url"].split("/")[2],
                        icon=engine.get("icon", "web-browser"),
                        result_type="web",
                        on_activate=lambda u=url: self._open_url(u),
                    )
                ]

        return []

    def _open_url(self, url: str):
        """Open URL in default browser via xdg-open and close launcher."""
        try:
            subprocess.Popen(
                ["xdg-open", url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            logger.warning("xdg-open not found, cannot open URL")

        from utils.helpers import close_launcher
        close_launcher()
