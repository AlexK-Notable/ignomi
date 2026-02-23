"""
Frequent Panel - Right panel showing apps ranked by frecency.

Features:
- Display top N apps by frecency score
- Auto-updates when frecency changes (GObject signal)
- Shows usage count badge
- Right-click context menu: remove from frequents, add to bookmarks
"""

from ignis import widgets
from ignis.services.applications import ApplicationsService
from ignis.menu_model import IgnisMenuModel, IgnisMenuItem
from gi.repository import Gtk, GLib
import sys
sys.path.insert(0, '/home/komi/repos/ignomi/launcher')

from utils.helpers import launch_app, add_bookmark, is_bookmarked, load_settings, get_monitor_under_cursor
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
            spacing=3,
            css_classes=["app-list"]
        )

        # Populate with frequent apps
        self._refresh_app_list()

        window = widgets.Window(
            namespace="ignomi-frequent",
            css_classes=["ignomi-window"],
            monitor=get_monitor_under_cursor(),
            anchor=["right", "top", "bottom"],
            exclusivity="exclusive",
            kb_mode="on_demand",  # Allow mouse interaction
            layer="top",
            default_width=320,
            visible=False,  # Start hidden, show via hotkey
            margin_top=8,  # Layer Shell margins (outside window, no background bleed)
            margin_bottom=8,
            margin_right=8,
            child=widgets.Box(
                vertical=True,
                vexpand=True,
                valign="center",
                child=[
                    # Panel background wraps content
                    widgets.Box(
                        vertical=True,
                        css_classes=["panel", "frequent-panel"],
                        child=[
                            # Header (horizontally centered)
                            widgets.Label(
                                label="Frequent",
                                css_classes=["panel-header"],
                                halign="center"
                            ),
                            # Scrollable app list (grows with content)
                            widgets.Scroll(
                                hexpand=True,
                                min_content_width=280,
                                propagate_natural_height=True,
                                child=self.app_list_box
                            )
                        ]
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
        # Content box (will hold menu after button creation)
        content_box = widgets.Box(
            spacing=8,
            child=[
                # App name and description (right-aligned, no truncation)
                widgets.Box(
                    vertical=True,
                    vexpand=True,
                    hexpand=True,
                    valign="center",
                    child=[
                        widgets.Label(
                            label=app.name,
                            css_classes=["app-name"],
                            halign="end",
                            wrap=True,
                            xalign=1.0
                        ),
                        widgets.Label(
                            label=app.description or "",
                            css_classes=["app-description"],
                            halign="end",
                            wrap=True,
                            wrap_mode="word_char",
                            lines=2,
                            xalign=1.0
                        )
                    ]
                ),
                # Icon with launch count below
                widgets.Box(
                    vertical=True,
                    valign="center",
                    halign="end",
                    spacing=4,
                    child=[
                        widgets.Icon(
                            image=app.icon,
                            pixel_size=48,
                            css_classes=["app-icon"]
                        ),
                        widgets.Label(
                            label=f"{launch_count}×",
                            css_classes=["frecency-count"],
                            halign="center"
                        )
                    ]
                )
            ]
        )

        button = widgets.Button(
            css_classes=["app-item"],
            on_click=lambda x, app=app: self._on_app_click(app),
            child=content_box
        )

        # Create context menu (after button exists for visual feedback reference)
        menu = self._create_context_menu(app, button)
        content_box.append(menu)

        # Add right-click handler to show context menu
        gesture = Gtk.GestureClick()
        gesture.set_button(3)  # Right click
        gesture.connect("pressed", lambda g, n, x, y, m=menu: m.popup())
        button.add_controller(gesture)

        return button

    def _create_context_menu(self, app, button):
        """Create context menu for a frequent app."""
        return widgets.PopoverMenu(
            model=IgnisMenuModel(
                IgnisMenuItem(
                    label="Remove from frequents",
                    on_activate=lambda x, a=app: self._remove_from_frequents(a),
                ),
                IgnisMenuItem(
                    label="Add to bookmarks",
                    on_activate=lambda x, a=app, b=button: self._add_to_bookmarks(a, b),
                ),
            )
        )

    def _on_app_click(self, app):
        """Launch app when clicked."""
        close_delay = self.settings["launcher"]["close_delay_ms"]
        launch_app(app, self.frecency, close_delay)

    def _remove_from_frequents(self, app):
        """Remove app from frecency tracking."""
        self.frecency.clear_stats(app.id)
        # UI refreshes automatically via frecency "changed" signal

    def _add_to_bookmarks(self, app, button):
        """Add app to bookmarks."""
        if not is_bookmarked(app.id):
            add_bookmark(app.id)

            # Visual feedback: Add pulse animation CSS class
            button.add_css_class("bookmark-added")

            # Remove the CSS class after animation completes (300ms)
            GLib.timeout_add(300, lambda: button.remove_css_class("bookmark-added"))

            # Refresh bookmarks panel to show new item
            from ignis.app import IgnisApp
            app_instance = IgnisApp.get_default()
            bookmarks_window = app_instance.get_window("ignomi-bookmarks")
            if bookmarks_window and hasattr(bookmarks_window, 'panel'):
                bookmarks_window.panel.refresh_from_disk()

    def _on_visibility_changed(self, window, param):
        """Update monitor placement when window becomes visible."""
        if window.get_visible():
            # Window is being shown - update to monitor under cursor
            cursor_monitor = get_monitor_under_cursor()
            if window.monitor != cursor_monitor:
                window.monitor = cursor_monitor
