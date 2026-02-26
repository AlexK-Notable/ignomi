"""
Web Search Handler - Open web searches in the default browser.

Triggers on prefix patterns:
  ? query     → Default search engine
  g: query    → Google
  w: query    → Wikipedia
  gh: query   → GitHub
  yt: query   → YouTube

Search engines are configurable via settings.toml [web_search] section.
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

    def __init__(self, engines: dict = None):
        self.engines = engines or DEFAULT_ENGINES

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

                url = engine["url"].format(
                    query=urllib.parse.quote_plus(search_term)
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
