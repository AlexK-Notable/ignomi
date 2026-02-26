"""
Bookmarks Panel - Left panel showing user-curated favorite applications.

Features:
- Load apps from bookmarks.json
- Display with icons and labels
- Right-click context menu: remove from bookmarks
- Drag-and-drop reordering
- Auto-saves changes
"""

import os
import sys

from gi.repository import Gdk, GObject, Gtk
from ignis.menu_model import IgnisMenuItem, IgnisMenuModel
from ignis.services.applications import ApplicationsService

from ignis import widgets

# Add launcher directory to path dynamically (works from any location/worktree)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.frecency import get_frecency_service
from utils.helpers import (
    clear_container,
    find_app_by_id,
    get_monitor_under_cursor,
    launch_app,
    load_bookmarks,
    load_settings,
    save_bookmarks,
    update_window_monitor,
)


class BookmarksPanel:
    """
    Left panel displaying user's bookmarked applications.

    Manages bookmark persistence and provides drag-drop reordering.
    """

    def __init__(self):
        self.apps_service = ApplicationsService.get_default()
        self.frecency = get_frecency_service()
        self.settings = load_settings()

        # Load bookmarks from JSON
        bookmark_ids = load_bookmarks()
        self.bookmarks = [app for app_id in bookmark_ids
                          if (app := find_app_by_id(app_id))]

        # Track drag state
        self.drag_source_index = None

    def create_window(self):
        """
        Create the bookmarks panel window.

        Animations are handled by Hyprland compositor layerrules,
        not by GTK Revealer. Using plain Window avoids the dual-animation
        conflict that caused visual artifacts.

        Returns:
            widgets.Window positioned on left edge
        """
        # Create scrollable app list
        self.app_list_box = widgets.Box(
            vertical=True,
            spacing=3,
            css_classes=["app-list"]
        )

        # Populate with bookmark buttons
        self._refresh_app_list()

        # Panel content
        content = widgets.Box(
            vertical=True,
            vexpand=True,
            valign="center",
            child=[
                widgets.Box(
                    vertical=True,
                    css_classes=["panel", "bookmarks-panel"],
                    child=[
                        widgets.Label(
                            label="Bookmarks",
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
            namespace="ignomi-bookmarks",
            css_classes=["ignomi-window"],
            monitor=get_monitor_under_cursor(),
            anchor=["left", "top", "bottom"],
            exclusivity="ignore",
            kb_mode="on_demand",
            layer="overlay",
            default_width=320,
            visible=False,
            margin_top=8,
            margin_bottom=8,
            margin_left=8,
            child=content,
        )

        window.connect("notify::visible", self._on_visibility_changed)

        return window

    def _refresh_app_list(self):
        """Rebuild the app list from current bookmarks."""
        clear_container(self.app_list_box)

        for index, app in enumerate(self.bookmarks):
            button = self._create_app_button(app, index)
            self.app_list_box.append(button)

    def _create_app_button(self, app, index):
        """
        Create a button for an app with drag-drop support.

        Args:
            app: Application object
            index: Position in bookmark list

        Returns:
            widgets.Button with icon, label, and drag-drop
        """
        # Create context menu
        menu = self._create_context_menu(app)

        # Main button
        button = widgets.Button(
            css_classes=["app-item"],
            on_click=lambda x, app=app: self._on_app_click(app),
            child=widgets.Box(
                spacing=8,
                child=[
                    # App icon on the left
                    widgets.Icon(
                        image=app.icon,
                        pixel_size=48,
                        css_classes=["app-icon"]
                    ),
                    # App name and description (left-aligned, no truncation)
                    widgets.Box(
                        vertical=True,
                        vexpand=True,
                        hexpand=True,
                        valign="center",
                        child=[
                            widgets.Label(
                                label=app.name,
                                css_classes=["app-name"],
                                halign="start",
                                wrap=True,
                                xalign=0.0
                            ),
                            widgets.Label(
                                label=app.description or "",
                                css_classes=["app-description"],
                                halign="start",
                                wrap=True,
                                wrap_mode="word_char",
                                lines=2,
                                xalign=0.0
                            )
                        ]
                    ),
                    # Hidden context menu (must be child of button content)
                    menu
                ]
            )
        )

        # Add right-click handler to show context menu
        gesture = Gtk.GestureClick()
        gesture.set_button(3)  # Right click
        gesture.connect("pressed", lambda g, n, x, y, m=menu: m.popup())
        button.add_controller(gesture)

        # Add drag source
        drag_source = Gtk.DragSource()
        drag_source.set_actions(Gdk.DragAction.MOVE)
        drag_source.connect("prepare", lambda src, x, y, idx=index: self._on_drag_prepare(idx))
        drag_source.connect("drag-begin", lambda src, drag: self._on_drag_begin())
        button.add_controller(drag_source)

        # Add drop target
        drop_target = Gtk.DropTarget.new(GObject.TYPE_STRING, Gdk.DragAction.MOVE)
        drop_target.connect("drop", lambda tgt, val, x, y, idx=index: self._on_drop(idx))
        drop_target.connect("enter", lambda tgt, x, y: self._on_drop_enter(button))
        drop_target.connect("leave", lambda tgt: self._on_drop_leave(button))
        button.add_controller(drop_target)

        return button

    def _on_app_click(self, app):
        """Launch app when clicked."""
        close_delay = self.settings["launcher"]["close_delay_ms"]
        launch_app(app, self.frecency, close_delay)

    def _create_context_menu(self, app):
        """Create context menu for a bookmarked app."""
        return widgets.PopoverMenu(
            model=IgnisMenuModel(
                IgnisMenuItem(
                    label="Remove from bookmarks",
                    on_activate=lambda x, a=app: self._remove_from_bookmarks(a),
                ),
            )
        )

    def _remove_from_bookmarks(self, app):
        """Remove app from bookmarks."""
        # Remove from list
        self.bookmarks = [a for a in self.bookmarks if a.id != app.id]

        # Save to disk
        bookmark_ids = [a.id for a in self.bookmarks]
        save_bookmarks(bookmark_ids)

        # Refresh UI
        self._refresh_app_list()

    # Drag-and-drop handlers

    def _on_drag_prepare(self, index):
        """Prepare drag operation."""
        self.drag_source_index = index
        # Return content provider with app ID
        app_id = self.bookmarks[index].id
        return Gdk.ContentProvider.new_for_value(GObject.Value(str, app_id))

    def _on_drag_begin(self):
        """Drag operation started."""
        pass

    def _on_drop(self, drop_index):
        """
        Handle drop operation - reorder bookmarks.

        Args:
            drop_index: Target position

        Returns:
            True if drop handled
        """
        if self.drag_source_index is None:
            return False

        # Don't do anything if dropping in same place
        if self.drag_source_index == drop_index:
            return True

        # Reorder bookmarks list
        app = self.bookmarks.pop(self.drag_source_index)

        # Adjust target index if needed
        if self.drag_source_index < drop_index:
            drop_index -= 1

        self.bookmarks.insert(drop_index, app)

        # Save new order
        bookmark_ids = [a.id for a in self.bookmarks]
        save_bookmarks(bookmark_ids)

        # Refresh UI
        self._refresh_app_list()

        return True

    def _on_drop_enter(self, button):
        """Visual feedback when drag enters drop zone."""
        button.add_css_class("drag-hover")

    def _on_drop_leave(self, button):
        """Remove visual feedback when drag leaves."""
        button.remove_css_class("drag-hover")

    def refresh_from_disk(self):
        """Reload bookmarks from disk and refresh UI (can be called externally)."""
        bookmark_ids = load_bookmarks()
        self.bookmarks = [app for app_id in bookmark_ids
                          if (app := find_app_by_id(app_id))]
        self._refresh_app_list()

    def _on_visibility_changed(self, window, param):
        """Update monitor placement when window becomes visible."""
        if window.get_visible():
            update_window_monitor(window)
