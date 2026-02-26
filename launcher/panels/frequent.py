"""
Frequent Panel - Right panel showing apps ranked by frecency.

Features:
- Display top N apps by frecency score
- Auto-updates when frecency changes (GObject signal)
- Shows usage count badge
- Right-click context menu: remove from frequents, add to bookmarks
"""

import os
import sys

from gi.repository import Gtk
from ignis.menu_model import IgnisMenuItem, IgnisMenuModel
from ignis.services.applications import ApplicationsService

from ignis import widgets

# Add launcher directory to path dynamically (works from any location/worktree)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.frecency import get_frecency_service
from utils.helpers import (
    add_bookmark_with_refresh,
    clear_container,
    find_app_by_id,
    get_monitor_under_cursor,
    launch_app,
    load_settings,
    update_window_monitor,
)


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
        for app_id, score, count, _last_launch in top_data:
            app = find_app_by_id(app_id)
            if app:
                apps.append((app, score, count))

        return apps

    def create_window(self):
        """
        Create the frequent apps panel window.

        Animations are handled by Hyprland compositor layerrules,
        not by GTK Revealer. Using plain Window avoids the dual-animation
        conflict that caused visual artifacts.

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

        # Panel content
        content = widgets.Box(
            vertical=True,
            vexpand=True,
            valign="center",
            child=[
                widgets.Box(
                    vertical=True,
                    css_classes=["panel", "frequent-panel"],
                    child=[
                        widgets.Label(
                            label="Frequent",
                            css_classes=["panel-header"],
                            halign="center"
                        ),
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

        window = widgets.Window(
            namespace="ignomi-frequent",
            css_classes=["ignomi-window"],
            monitor=get_monitor_under_cursor(),
            anchor=["right", "top", "bottom"],
            exclusivity="ignore",
            kb_mode="on_demand",
            layer="overlay",
            default_width=320,
            visible=False,
            margin_top=8,
            margin_bottom=8,
            margin_right=8,
            child=content,
        )

        window.connect("notify::visible", self._on_visibility_changed)

        return window

    def _refresh_apps(self):
        """Callback when frecency data changes."""
        self.top_apps = self._get_top_apps()
        self._refresh_app_list()

    def _refresh_app_list(self):
        """Rebuild the app list from current top apps."""
        clear_container(self.app_list_box)

        # Add frequent app buttons
        if self.top_apps:
            for app, _score, count in self.top_apps:
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
        add_bookmark_with_refresh(app.id, button)

    def _on_visibility_changed(self, window, param):
        """Update monitor placement when window becomes visible."""
        if window.get_visible():
            update_window_monitor(window)
