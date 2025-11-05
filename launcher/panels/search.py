"""
Search Panel - Center panel with search entry and filtered results.

Features:
- Search entry with placeholder text
- Real-time filtering using ApplicationsService.search()
- Display results with icons and labels
- Right-click to add to bookmarks
- Keyboard navigation (arrow keys, Enter to launch)
"""

from ignis import widgets
from ignis.services.applications import ApplicationsService
from gi.repository import Gtk, GLib
import sys
sys.path.insert(0, '/home/komi/repos/ignomi/launcher')

from utils.helpers import launch_app, add_bookmark, is_bookmarked, get_focused_monitor
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
            widgets.Window positioned at top center
        """
        # Search entry
        self.search_entry = widgets.Entry(
            placeholder_text="Search applications...",
            css_classes=["search-entry"],
            on_change=lambda x: self._on_search_changed()
        )

        # Results container
        self.results_box = widgets.Box(
            vertical=True,
            spacing=2,
            css_classes=["search-results"]
        )

        # Initial population
        self._update_results()

        window = widgets.Window(
            namespace="ignomi-search",
            monitor=get_focused_monitor(),
            anchor=["top"],
            exclusivity="normal",
            kb_mode="on_demand",  # Allow interaction while focused
            layer="top",
            default_width=600,
            default_height=700,
            child=widgets.Box(
                vertical=True,
                css_classes=["panel", "search-panel"],
                child=[
                    # Search entry
                    self.search_entry,
                    # Scrollable results
                    widgets.Scroll(
                        vexpand=True,
                        hexpand=True,
                        child=self.results_box
                    )
                ]
            )
        )

        # Add Escape key handler to close launcher
        key_controller = Gtk.EventControllerKey()
        key_controller.connect("key-pressed", self._on_key_press)
        window.add_controller(key_controller)

        # Add signal handler to update monitor when window becomes visible
        window.connect("notify::visible", self._on_visibility_changed)

        return window

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
        # Clear existing (GTK4 way)
        child = self.results_box.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self.results_box.remove(child)
            child = next_child

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
            widgets.Button with icon and label
        """
        button = widgets.Button(
            css_classes=["app-item", "result-item"],
            on_click=lambda x, app=app: self._on_app_click(app),
            child=widgets.Box(
                spacing=12,
                child=[
                    # App icon
                    widgets.Icon(
                        image=app.icon,
                        pixel_size=32,
                        css_classes=["app-icon"]
                    ),
                    # App name and description
                    widgets.Box(
                        vertical=True,
                        vexpand=True,
                        valign="center",
                        child=[
                            widgets.Label(
                                label=app.name,
                                css_classes=["app-name"],
                                halign="start",
                                ellipsize="end",
                                max_width_chars=40
                            ),
                            widgets.Label(
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
        gesture.connect("pressed", lambda g, n, x, y, app=app, btn=button: self._on_right_click(app, btn))
        button.add_controller(gesture)

        return button

    def _on_app_click(self, app):
        """Launch app when clicked."""
        from utils.helpers import load_settings
        settings = load_settings()
        close_delay = settings["launcher"]["close_delay_ms"]
        launch_app(app, self.frecency, close_delay)

    def _on_right_click(self, app, button):
        """Add app to bookmarks on right-click."""
        if not is_bookmarked(app.id):
            add_bookmark(app.id)

            # Visual feedback: Add pulse animation CSS class
            button.add_css_class("bookmark-added")

            # Remove the CSS class after animation completes (300ms)
            GLib.timeout_add(300, lambda: button.remove_css_class("bookmark-added"))

            print(f"Added {app.name} to bookmarks")

    def _on_visibility_changed(self, window, param):
        """Update monitor placement when window becomes visible."""
        if window.get_visible():
            # Window is being shown - update to current focused monitor
            focused = get_focused_monitor()
            if window.monitor != focused:
                window.monitor = focused

    def _on_key_press(self, controller, keyval, keycode, state):
        """Handle keyboard events - close on Escape."""
        from gi.repository import Gdk
        from utils.helpers import close_launcher

        if keyval == Gdk.KEY_Escape:
            close_launcher()
            return True
        return False
