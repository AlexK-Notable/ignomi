"""
Search Panel - Center panel with search entry and filtered results.

Features:
- Search entry with placeholder text
- Real-time filtering using ApplicationsService.search()
- Display results with icons and labels
- Right-click to add to bookmarks
- Keyboard navigation (arrow keys, Enter to launch)
"""

from ignis.widgets import Widget
from ignis.services.applications import ApplicationsService
from gi.repository import Gtk
import sys
sys.path.insert(0, '/home/komi/repos/ignomi/launcher')

from utils.helpers import launch_app, add_bookmark, is_bookmarked
from services.frecency import get_frecency_service


class SearchPanel:
    """
    Center panel providing app search functionality.

    Filters all installed applications based on user input.
    """

    def __init__(self):
        self.apps_service = ApplicationsService.get_default()
        self.frecency = get_frecency_service()

        self.all_apps = self.apps_service.apps
        self.filtered_apps = self.all_apps[:20]  # Show top 20 by default

        # Widgets (created in create_window)
        self.search_entry = None
        self.results_box = None

    def create_window(self):
        """
        Create the search panel window.

        Returns:
            Widget.Window positioned at top center
        """
        # Search entry
        self.search_entry = Widget.Entry(
            placeholder_text="Search applications...",
            css_classes=["search-entry"],
            on_change=lambda x: self._on_search_changed()
        )

        # Results container
        self.results_box = Widget.Box(
            vertical=True,
            spacing=2,
            css_classes=["search-results"]
        )

        # Initial population
        self._update_results()

        return Widget.Window(
            namespace="ignomi-search",
            monitor=0,
            anchor=["top"],
            exclusive=False,
            keyboard_mode="exclusive",  # Gets keyboard focus
            layer="top",
            child=Widget.Box(
                vertical=True,
                css_classes=["panel", "search-panel"],
                child=[
                    # Search entry
                    self.search_entry,
                    # Scrollable results
                    Widget.ScrolledWindow(
                        vexpand=True,
                        hexpand=True,
                        min_content_width=480,
                        max_content_height=600,
                        child=self.results_box
                    )
                ]
            )
        )

    def _on_search_changed(self):
        """Handle search entry text changes."""
        query = self.search_entry.text

        if query and query.strip():
            # Filter using Ignis built-in search
            self.filtered_apps = self.apps_service.search(
                self.all_apps,
                query
            )
        else:
            # Show default top apps
            self.filtered_apps = self.all_apps[:20]

        self._update_results()

    def _update_results(self):
        """Rebuild results list from filtered apps."""
        # Clear existing
        for child in self.results_box.get_children():
            self.results_box.remove(child)

        # Add result buttons
        for app in self.filtered_apps[:30]:  # Max 30 results
            button = self._create_result_button(app)
            self.results_box.append(button)

    def _create_result_button(self, app):
        """
        Create a button for a search result.

        Args:
            app: Application object

        Returns:
            Widget.Button with icon and label
        """
        button = Widget.Button(
            css_classes=["app-item", "result-item"],
            on_click=lambda x, app=app: self._on_app_click(app),
            child=Widget.Box(
                spacing=12,
                child=[
                    # App icon
                    Widget.Icon(
                        image=app.icon,
                        pixel_size=32,
                        css_classes=["app-icon"]
                    ),
                    # App name and description
                    Widget.Box(
                        vertical=True,
                        vexpand=True,
                        valign="center",
                        child=[
                            Widget.Label(
                                label=app.name,
                                css_classes=["app-name"],
                                halign="start",
                                ellipsize="end",
                                max_width_chars=40
                            ),
                            Widget.Label(
                                label=app.description or "",
                                css_classes=["app-description"],
                                halign="start",
                                ellipsize="end",
                                max_width_chars=50
                            )
                        ]
                    )
                ]
            )
        )

        # Add right-click handler (add to bookmarks)
        gesture = Gtk.GestureClick()
        gesture.set_button(3)  # Right click
        gesture.connect("pressed", lambda g, n, x, y, app=app: self._on_right_click(app))
        button.add_controller(gesture)

        return button

    def _on_app_click(self, app):
        """Launch app when clicked."""
        from utils.helpers import load_settings
        settings = load_settings()
        close_delay = settings["launcher"]["close_delay_ms"]
        launch_app(app, self.frecency, close_delay)

    def _on_right_click(self, app):
        """Add app to bookmarks on right-click."""
        if not is_bookmarked(app.id):
            add_bookmark(app.id)

            # TODO: Visual feedback (pulse animation)
            # For now, just print confirmation
            print(f"Added {app.name} to bookmarks")
