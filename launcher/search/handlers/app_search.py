"""
App Search Handler — tiered match scoring with frecency tiebreak.

`fuzz.WRatio` alone produced bad rankings for short queries: typing
"vesk" returned RustDesk and GitHub Desktop above Vesktop because all
three score similarly under WRatio (they share the substring "esk"),
even though only Vesktop is an actual prefix match.

This handler replaces the single-scorer approach with five descending
tiers. Each tier carries a base score so a worse-tier match can never
beat a better-tier match. Within a tier, shorter names rank higher
(more specific) and a small log-scaled frecency boost gives the user's
most-launched apps a tiebreak advantage — capped so it never crosses
tier boundaries.

Tiers (descending priority):
  1. Exact name match                         → 1000
  2. Name starts with query                   → 950 - len(name)
  3. Any token in name starts with query      → 850 - len(name)
  4. Query appears anywhere in name           → 750 - len(name)
  5. Fuzzy WRatio match (rapidfuzz only)      → raw 50–100

Install fuzzy search: pipx inject ignis rapidfuzz
"""

import math

from ignis.services.applications import ApplicationsService
from search.router import ResultItem

try:
    from rapidfuzz import fuzz
    HAS_RAPIDFUZZ = True
except ImportError:
    HAS_RAPIDFUZZ = False


_TIER_EXACT = 1000
_TIER_PREFIX = 950
_TIER_WORD_PREFIX = 850
_TIER_SUBSTRING = 750
# Tier 5 (fuzzy) keeps its raw 0–100 WRatio score, well below all above.

# Caps. Keep length penalty + frecency boost smaller than the 100-point
# tier gap so ranking stays tier-stable.
_LENGTH_PENALTY_CAP = 50
_FRECENCY_BOOST_CAP = 20


class AppSearchHandler:
    """Search installed applications with tiered + frecency-boosted scoring."""

    name = "app_search"
    priority = 1000

    # Optional metadata, read by the shortcuts screen to document itself.
    # No prefix: this is the always-matches fallback.
    description = "Default — searches installed applications"
    example = "firefox"

    def __init__(
        self,
        max_results: int = 30,
        fuzzy_threshold: int = 50,
        frecency_service=None,
    ):
        self.apps_service = ApplicationsService.get_default()
        self.max_results = max_results
        self.fuzzy_threshold = fuzzy_threshold
        self.frecency_service = frecency_service

    def matches(self, query: str) -> bool:
        return True

    def get_results(self, query: str) -> list[ResultItem]:
        all_apps = self.apps_service.apps

        if not query or not query.strip():
            return self._apps_to_results(all_apps[:20])

        scored: list[tuple[float, object]] = []
        for app in all_apps:
            score = self._score_app(query, app)
            if score is not None:
                scored.append((score, app))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [self._app_to_result(app) for _, app in scored[: self.max_results]]

    def _score_app(self, query: str, app) -> float | None:
        """Compute a relevance score; None means no match."""
        q = query.lower().strip()
        if not q:
            return None

        name = (app.name or "").lower()
        if not name:
            return None

        length_penalty = min(_LENGTH_PENALTY_CAP, len(name))

        if name == q:
            base = _TIER_EXACT
        elif name.startswith(q):
            base = _TIER_PREFIX - length_penalty
        elif any(word.startswith(q) for word in name.split()):
            base = _TIER_WORD_PREFIX - length_penalty
        elif q in name:
            base = _TIER_SUBSTRING - length_penalty
        elif HAS_RAPIDFUZZ:
            fuzzy = fuzz.WRatio(q, name)
            if fuzzy < self.fuzzy_threshold:
                return None
            base = fuzzy
        else:
            return None

        return base + self._frecency_boost(app.id)

    def _frecency_boost(self, app_id: str) -> float:
        """Log-scaled boost capped at _FRECENCY_BOOST_CAP."""
        service = getattr(self, "frecency_service", None)
        if service is None:
            return 0.0
        try:
            raw = service.get_frecency_score(app_id)
        except Exception:
            return 0.0
        if raw <= 0:
            return 0.0
        return min(_FRECENCY_BOOST_CAP, math.log1p(raw) * 3)

    def _app_to_result(self, app) -> ResultItem:
        return ResultItem(
            title=app.name,
            description=app.description or "",
            icon=app.icon,
            result_type="app",
            app=app,
        )

    def _apps_to_results(self, apps) -> list[ResultItem]:
        return [self._app_to_result(app) for app in apps]
