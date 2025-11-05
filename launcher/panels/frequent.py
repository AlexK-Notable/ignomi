"""
Frequent Panel - Right panel showing apps ranked by frecency.

Features:
- Display top N apps by frecency score
- Auto-updates when frecency changes (GObject signal)
- Shows usage count badge
- Right-click to add to bookmarks
"""

from ignis import widgets
from ignis.services.applications import ApplicationsService
from gi.repository import Gtk, GLib
import sys
sys.path.insert(0, '/home/komi/repos/ignomi/launcher')

from utils.helpers import launch_app, add_bookmark, is_bookmarked, load_settings, get_focused_monitor
from services.frecency import get_frecency_service


class FrequentPanel:
    """
    Right panel displaying frequently-used applications.

    Ranks apps using frecency algorithm (frequency × recency).
    """

    def __init__(self):
        self.apps_service = ApplicationsService.get_default()
        self.frecency = get_frecency_service()

        # Connect to frecency changes
        self.frecency.connect("changed", lambda x: self._refresh_apps())

        # Load settings
        self.settings = load_settings()
        self.max_items = self.settings["frecency"]["max_items"]
        self.min_launches = self.settings["frecency"]["min_launches"]

        # Load top apps
        self.top_apps = self._get_top_apps()

        # Widgets (created in create_window)
        self.app_list_box = None

    def _get_top_apps(self):
        """
        Get top apps from frecency service.

        Returns:
            List of tuples: (app, frecency_score, launch_count)
        """
        top_data = self.frecency.get_top_apps(
            limit=self.max_items,
            min_launches=self.min_launches
        )

        apps = []
        for app_id, score, count, last_launch in top_data:
            app = self._find_app_by_id(app_id)
            if app:
                apps.append((app, score, count))

        return apps

    def _find_app_by_id(self, app_id):
        """Find Application object by desktop ID."""
        for app in self.apps_service.apps:
            if app.id == app_id:
                return app
        return None

    def create_window(self):
        """
        Create the frequent apps panel window.

        Returns:
            widgets.Window positioned on right edge
        """
        # Create app list container
        self.app_list_box = widgets.Box(
            vertical=True,
            spacing=4,
            css_classes=["app-list"]
        )

        # Populate with frequent apps
        self._refresh_app_list()

        window = widgets.Window(
            namespace="ignomi-frequent",
            monitor=get_focused_monitor(),
            anchor=["right", "top", "bottom"],
            exclusivity="exclusive",
            kb_mode="on_demand",  # Allow mouse interaction
            layer="top",
            default_width=320,
            child=widgets.Box(
                vertical=True,
                css_classes=["panel", "frequent-panel"],
                child=[
                    # Header
                    widgets.Label(
                        label="Frequent",
                        css_classes=["panel-header"],
                        halign="start"
                    ),
                    # Scrollable app list
                    widgets.Scroll(
                        vexpand=True,
                        hexpand=True,
                        min_content_width=280,
                        child=self.app_list_box
                    )
                ]
            )
        )

        # Add signal handler to update monitor when window becomes visible
        window.connect("notify::visible", self._on_visibility_changed)

        return window

    def _refresh_apps(self):
        """Callback when frecency data changes."""
        self.top_apps = self._get_top_apps()
        self._refresh_app_list()

    def _refresh_app_list(self):
        """Rebuild the app list from current top apps."""
        # Clear existing (GTK4 way)
        child = self.app_list_box.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self.app_list_box.remove(child)
            child = next_child

        # Add frequent app buttons
        if self.top_apps:
            for app, score, count in self.top_apps:
                button = self._create_app_button(app, count)
                self.app_list_box.append(button)
        else:
            # Show empty state
            empty_label = widgets.Label(
                label="No frequent apps yet\n\nLaunch apps to build history",
                css_classes=["empty-state"],
                justify="center"
            )
            self.app_list_box.append(empty_label)

    def _create_app_button(self, app, launch_count):
        """
        Create a button for a frequent app.

        Args:
            app: Application object
            launch_count: Number of times launched

        Returns:
            widgets.Button with icon, label, and usage badge
        """
        button = widgets.Button(
            css_classes=["app-item"],
            on_click=lambda x, app=app: self._on_app_click(app),
            child=widgets.Box(
                spacing=12,
                child=[
                    # App icon
                    widgets.Icon(
                        image=app.icon,
                        pixel_size=48,
                        css_classes=["app-icon"]
                    ),
                    # App name, description, and count
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
                                max_width_chars=20
                            ),
                            widgets.Label(
                                label=app.description or "",
                                css_classes=["app-description"],
                                halign="start",
                                ellipsize="end",
                                max_width_chars=25
                            ),
                            widgets.Label(
                                label=f"Launched {launch_count}× ",
                                css_classes=["frecency-count"],
                                halign="start"
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
        close_delay = self.settings["launcher"]["close_delay_ms"]
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
