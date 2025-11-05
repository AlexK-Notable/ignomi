"""
Search Panel - Center panel with search entry and filtered results.

Features:
- Search entry with placeholder text
- Real-time filtering using ApplicationsService.search()
- Display results with icons and labels (center-aligned)
- Right-click to add to bookmarks with seamless refresh
- Keyboard navigation (arrow keys, Enter to launch)
- Auto-focus search field when launcher opens
- Clear search term when launcher closes
"""

from ignis import widgets
from ignis.services.applications import ApplicationsService
from gi.repository import Gtk, GLib, Gdk
import sys
sys.path.insert(0, '/home/komi/repos/ignomi/launcher')

from utils.helpers import launch_app, add_bookmark, is_bookmarked, get_monitor_under_cursor
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

        # Keyboard navigation
        self.selected_index = -1  # -1 means no selection
        self.result_buttons = []  # Track buttons for keyboard navigation

    def create_window(self):
        """
        Create the search panel window.

        Returns:
            widgets.Window positioned at top center
        """
        # Search entry with center alignment
        self.search_entry = widgets.Entry(
            placeholder_text="Search applications...",
            css_classes=["search-entry"],
            on_change=lambda x: self._on_search_changed()
        )
        # Center the text in the entry
        self.search_entry.set_alignment(0.5)

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
            monitor=get_monitor_under_cursor(),
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

        # Add keyboard event controller
        key_controller = Gtk.EventControllerKey()
        key_controller.connect("key-pressed", self._on_key_press)
        window.add_controller(key_controller)

        # Add signal handler to update monitor and handle focus when window becomes visible
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

        # Reset keyboard selection when search changes
        self.selected_index = -1
        self._update_results()

    def _update_results(self):
        """Rebuild results list from filtered apps."""
        # Clear existing (GTK4 way)
        child = self.results_box.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self.results_box.remove(child)
            child = next_child

        # Reset button tracking
        self.result_buttons = []

        # Add result buttons
        for app in self.filtered_apps[:30]:  # Max 30 results
            button = self._create_result_button(app)
            self.results_box.append(button)
            self.result_buttons.append(button)

        # Apply selection highlight if index is valid
        self._update_selection_highlight()

    def _create_result_button(self, app):
        """
        Create a button for a search result with center-aligned layout.

        Args:
            app: Application object

        Returns:
            widgets.Button with icon and label
        """
        button = widgets.Button(
            css_classes=["app-item", "result-item"],
            child=widgets.Box(
                halign="center",  # Center entire entry
                child=[
                    # Vertical stack: [Icon+Name] above [Description]
                    widgets.Box(
                        vertical=True,
                        spacing=4,
                        child=[
                            # Icon and app name on same line
                            widgets.Box(
                                spacing=8,
                                halign="center",
                                valign="center",
                                child=[
                                    widgets.Icon(
                                        image=app.icon,
                                        pixel_size=24,
                                        css_classes=["app-icon"],
                                    ),
                                    widgets.Label(
                                        label=app.name,
                                        css_classes=["app-name", "search-app-name"],
                                        ellipsize="end",
                                        max_width_chars=35,
                                    ),
                                ],
                            ),
                            # Description on its own line below
                            widgets.Label(
                                label=app.description or "",
                                css_classes=["app-description", "search-app-description"],
                                halign="center",
                                xalign=0.5,
                                ellipsize="end",
                                max_width_chars=45,
                            ),
                        ],
                    )
                ],
            ),
        )

        # Left-click to launch
        gesture_left = Gtk.GestureClick()
        gesture_left.set_button(1)  # Left click
        gesture_left.connect("pressed", lambda g, n, x, y, app=app: self._on_app_click(app))
        button.add_controller(gesture_left)

        # Right-click to add to bookmarks (pass button for visual feedback)
        gesture_right = Gtk.GestureClick()
        gesture_right.set_button(3)  # Right click
        gesture_right.connect("pressed", lambda g, n, x, y, app=app, btn=button: self._on_right_click(app, btn))
        button.add_controller(gesture_right)

        return button

    def _on_app_click(self, app):
        """Launch app when clicked."""
        from utils.helpers import load_settings
        settings = load_settings()
        close_delay = settings["launcher"]["close_delay_ms"]
        launch_app(app, self.frecency, close_delay)

    def _on_right_click(self, app, button):
        """Add app to bookmarks with visual feedback and seamless panel refresh."""
        if not is_bookmarked(app.id):
            # Add bookmark to file
            add_bookmark(app.id)

            # Visual feedback: Add pulse animation CSS class
            button.add_css_class("bookmark-added")

            # Remove the CSS class after animation completes (300ms)
            GLib.timeout_add(300, lambda: button.remove_css_class("bookmark-added"))

            print(f"Added {app.name} to bookmarks")

            # Directly refresh bookmarks panel (no flicker!)
            from ignis.app import IgnisApp
            app_instance = IgnisApp.get_default()
            bookmarks_window = app_instance.get_window("ignomi-bookmarks")
            if bookmarks_window and hasattr(bookmarks_window, 'panel'):
                # Call refresh method directly - seamless update
                bookmarks_window.panel.refresh_from_disk()

    def _on_visibility_changed(self, window, param):
        """Handle visibility changes - clear search on close, grab focus on open."""
        if window.get_visible():
            # Window is being shown - update to monitor under cursor
            cursor_monitor = get_monitor_under_cursor()
            if window.monitor != cursor_monitor:
                window.monitor = cursor_monitor

            # Grab focus with delay to allow animation to complete
            # Window animates into position, so we need to wait for it to settle
            # before calculating and moving cursor to search entry
            self._focus_retry_count = 0
            GLib.timeout_add(300, self._grab_entry_focus)  # 300ms for animation
        else:
            # Window is being hidden - clear search term for fresh start next time
            self.search_entry.set_text("")
            self.selected_index = -1  # Reset keyboard selection

    def _grab_entry_focus(self):
        """
        Move cursor to search entry to ensure focus.

        Instead of trying to grab focus programmatically (unreliable with layer-shell),
        we physically move the cursor to the search entry position.
        """
        import subprocess
        import json

        try:
            # Get current monitor info to calculate window position
            cursor_monitor_hyprland = get_monitor_under_cursor()

            # Need to get Hyprland monitor info (with actual coordinates)
            result = subprocess.run(['hyprctl', 'monitors', '-j'],
                                  capture_output=True, text=True, timeout=1)
            if result.returncode == 0:
                monitors = json.loads(result.stdout)

                # Find the monitor by matching through GTK->Hyprland translation
                from gi.repository import Gdk
                display = Gdk.Display.get_default()
                if display:
                    gtk_monitors = display.get_monitors()
                    if cursor_monitor_hyprland < gtk_monitors.get_n_items():
                        gtk_monitor = gtk_monitors.get_item(cursor_monitor_hyprland)
                        connector = gtk_monitor.get_connector()

                        # Find matching Hyprland monitor
                        for monitor in monitors:
                            if monitor['name'] == connector:
                                # Calculate search window position
                                # Window is 600px wide, centered on monitor
                                monitor_x = monitor['x']
                                monitor_y = monitor['y']
                                monitor_width = monitor['width']

                                # Window centered horizontally at top
                                window_x = monitor_x + (monitor_width - 600) // 2
                                window_y = monitor_y + 8  # margin from top

                                # Search entry is at top of window
                                entry_x = window_x + 300  # Center of 600px window horizontally
                                entry_y = window_y + 92   # Calibrated Y offset for search entry center

                                subprocess.run(['hyprctl', 'dispatch', 'movecursor',
                                              str(entry_x), str(entry_y)],
                                             capture_output=True)

                                # Give it a moment, then grab focus
                                self.search_entry.grab_focus()
                                break
        except Exception:
            # Fallback to just grabbing focus
            self.search_entry.grab_focus()

        return False  # Don't repeat

    def _on_key_press(self, controller, keyval, keycode, state):
        """Handle keyboard events - arrows for navigation, Enter to launch, Escape to close."""
        from utils.helpers import close_launcher

        # Escape - close launcher
        if keyval == Gdk.KEY_Escape:
            close_launcher()
            return True

        # No results - no navigation
        if not self.result_buttons:
            return False

        # Down arrow - move selection down
        if keyval == Gdk.KEY_Down:
            if self.selected_index < len(self.result_buttons) - 1:
                self.selected_index += 1
                self._update_selection_highlight()
                self._scroll_to_selected()
            return True

        # Up arrow - move selection up
        elif keyval == Gdk.KEY_Up:
            if self.selected_index > 0:
                self.selected_index -= 1
                self._update_selection_highlight()
                self._scroll_to_selected()
            elif self.selected_index == 0:
                # At top - return focus to search entry
                self.selected_index = -1
                self._update_selection_highlight()
                self.search_entry.grab_focus()
            return True

        # Enter - launch selected app
        elif keyval == Gdk.KEY_Return:
            if 0 <= self.selected_index < len(self.filtered_apps):
                app = self.filtered_apps[self.selected_index]
                self._on_app_click(app)
                return True

        return False

    def _update_selection_highlight(self):
        """Update visual highlight for keyboard navigation."""
        for i, button in enumerate(self.result_buttons):
            if i == self.selected_index:
                button.add_css_class("keyboard-selected")
            else:
                button.remove_css_class("keyboard-selected")

    def _scroll_to_selected(self):
        """Scroll to make selected item visible."""
        if 0 <= self.selected_index < len(self.result_buttons):
            selected_button = self.result_buttons[self.selected_index]
            # Request scroll to the button
            # Note: GTK4 doesn't have a direct "scroll to widget" method
            # The button will be visible if results box is properly configured
            selected_button.grab_focus()
