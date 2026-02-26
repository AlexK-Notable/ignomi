"""
App Search Handler - Application search with optional fuzzy matching.

When rapidfuzz is available, uses fuzzy matching for typo-tolerant search.
Falls back to Ignis ApplicationsService.search() otherwise.

Install fuzzy search: pipx inject ignis rapidfuzz
"""

from ignis.services.applications import ApplicationsService
from search.router import ResultItem

try:
    from rapidfuzz import fuzz, process
    HAS_RAPIDFUZZ = True
except ImportError:
    HAS_RAPIDFUZZ = False


class AppSearchHandler:
    """Search installed applications with optional fuzzy matching."""

    name = "app_search"
    priority = 1000

    def __init__(self, max_results: int = 30, fuzzy_threshold: int = 50):
        self.apps_service = ApplicationsService.get_default()
        self.max_results = max_results
        self.fuzzy_threshold = fuzzy_threshold

    def matches(self, query: str) -> bool:
        return True

    def get_results(self, query: str) -> list[ResultItem]:
        all_apps = self.apps_service.apps

        if not query or not query.strip():
            return self._apps_to_results(all_apps[:20])

        if HAS_RAPIDFUZZ:
            return self._fuzzy_search(query, all_apps)
        else:
            filtered = self.apps_service.search(all_apps, query)
            return self._apps_to_results(filtered[:self.max_results])

    def _fuzzy_search(self, query: str, all_apps) -> list[ResultItem]:
        """Fuzzy search using rapidfuzz weighted ratio against app names."""
        # Match against name only — descriptions dilute relevance
        choices = {app.id: app.name for app in all_apps}

        matches = process.extract(
            query,
            choices,
            scorer=fuzz.WRatio,
            limit=self.max_results,
            score_cutoff=self.fuzzy_threshold,
        )

        # matches: list of (matched_string, score, key)
        results = []
        for _matched_str, _score, app_id in matches:
            app = self._find_app(app_id, all_apps)
            if app:
                results.append(ResultItem(
                    title=app.name,
                    description=app.description or "",
                    icon=app.icon,
                    result_type="app",
                    app=app,
                ))

        return results

    def _find_app(self, app_id: str, all_apps):
        """Find app in list by ID."""
        for app in all_apps:
            if app.id == app_id:
                return app
        return None

    def _apps_to_results(self, apps) -> list[ResultItem]:
        """Convert Application objects to ResultItem list."""
        return [
            ResultItem(
                title=app.name,
                description=app.description or "",
                icon=app.icon,
                result_type="app",
                app=app,
            )
            for app in apps
        ]
