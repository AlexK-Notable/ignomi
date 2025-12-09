"""
Bookmarks Panel - Left panel showing user-curated favorite applications.

Features:
- Load apps from bookmarks.json
- Display with icons and labels
- Right-click to remove from bookmarks
- Drag-and-drop reordering
- Auto-saves changes
"""

from ignis import widgets
from ignis.services.applications import ApplicationsService
from gi.repository import Gtk, Gdk, GObject
import sys
sys.path.insert(0, '/home/komi/repos/ignomi/launcher')

from utils.helpers import load_bookmarks, save_bookmarks, launch_app, remove_bookmark, get_monitor_under_cursor
from services.frecency import get_frecency_service


class BookmarksPanel:
    """
    Left panel displaying user's bookmarked applications.

    Manages bookmark persistence and provides drag-drop reordering.
    """

    def __init__(self):
        self.apps_service = ApplicationsService.get_default()
        self.frecency = get_frecency_service()

        # Load bookmarks from JSON
        bookmark_ids = load_bookmarks()
        self.bookmarks = self._load_bookmark_apps(bookmark_ids)

        # Track drag state
        self.drag_source_index = None

    def _load_bookmark_apps(self, bookmark_ids):
        """
        Convert bookmark IDs to Application objects.

        Args:
            bookmark_ids: List of desktop file IDs

        Returns:
            List of Application objects (filters out not found)
        """
        apps = []
        for app_id in bookmark_ids:
            app = self._find_app_by_id(app_id)
            if app:
                apps.append(app)
        return apps

    def _find_app_by_id(self, app_id):
        """Find Application object by desktop ID."""
        for app in self.apps_service.apps:
            if app.id == app_id:
                return app
        return None

    def create_window(self):
        """
        Create the bookmarks panel window.

        Returns:
            widgets.Window positioned on left edge
        """
        # Create scrollable app list
        self.app_list_box = widgets.Box(
            vertical=True,
            spacing=4,
            css_classes=["app-list"]
        )

        # Populate with bookmark buttons
        self._refresh_app_list()

        window = widgets.Window(
            namespace="ignomi-bookmarks",
            css_classes=["ignomi-window"],
            monitor=get_monitor_under_cursor(),
            anchor=["left", "top", "bottom"],
            exclusivity="exclusive",
            kb_mode="on_demand",  # Allow mouse interaction
            layer="top",
            default_width=320,
            visible=False,  # Start hidden, show via hotkey
            margin_top=8,  # Layer Shell margins (outside window, no background bleed)
            margin_bottom=8,
            margin_left=8,
            child=widgets.Box(
                vertical=True,
                css_classes=["panel", "bookmarks-panel"],
                child=[
                    # Header
                    widgets.Label(
                        label="Bookmarks",
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

    def _refresh_app_list(self):
        """Rebuild the app list from current bookmarks."""
        # Clear existing (GTK4 way)
        child = self.app_list_box.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self.app_list_box.remove(child)
            child = next_child

        # Add bookmark buttons
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
        # Main button
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
                                max_width_chars=20
                            ),
                            widgets.Label(
                                label=app.description or "",
                                css_classes=["app-description"],
                                halign="start",
                                ellipsize="end",
                                max_width_chars=25
                            )
                        ]
                    )
                ]
            )
        )

        # Add right-click handler (remove from bookmarks)
        gesture = Gtk.GestureClick()
        gesture.set_button(3)  # Right click
        gesture.connect("pressed", lambda g, n, x, y, app=app: self._on_right_click(app))
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
        from utils.helpers import load_settings
        settings = load_settings()
        close_delay = settings["launcher"]["close_delay_ms"]
        launch_app(app, self.frecency, close_delay)

    def _on_right_click(self, app):
        """Remove app from bookmarks on right-click."""
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
        from utils.helpers import load_bookmarks

        # Reload bookmarks from disk
        bookmark_ids = load_bookmarks()

        # Convert IDs to app objects
        self.bookmarks = []
        for app_id in bookmark_ids:
            app = self._find_app_by_id(app_id)
            if app:
                self.bookmarks.append(app)

        # Refresh the UI
        self._refresh_app_list()

    def _on_visibility_changed(self, window, param):
        """Update monitor placement when window becomes visible."""
        if window.get_visible():
            # Window is being shown - update to monitor under cursor
            cursor_monitor = get_monitor_under_cursor()
            if window.monitor != cursor_monitor:
                window.monitor = cursor_monitor
