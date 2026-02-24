"""
Search Panel - Center panel with search entry and filtered results.

Features:
- Query router dispatches to typed handlers (app search, calculator, etc.)
- Real-time filtering with keyboard navigation
- Right-click to add apps to bookmarks
- Auto-focus search field when launcher opens
- Clear search term when launcher closes
"""

from ignis import widgets
from ignis.services.applications import ApplicationsService
from gi.repository import Gtk, GLib, Gdk
import sys
import os
# Add launcher directory to path dynamically (works from any location/worktree)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.helpers import (
    launch_app, get_monitor_under_cursor, load_settings,
    clear_container, add_bookmark_with_refresh, update_window_monitor,
)
from services.frecency import get_frecency_service
from search.router import QueryRouter, ResultItem
from search.handlers import (
    AppSearchHandler, CalculatorHandler,
    SystemControlsHandler, WebSearchHandler, CustomCommandsHandler,
)


class SearchPanel:
    """
    Center panel providing search functionality via pluggable query router.

    Handlers are registered with priorities — the first matching handler
    produces the results. App search is the fallback.
    """

    def __init__(self):
        self.apps_service = ApplicationsService.get_default()
        self.frecency = get_frecency_service()
        self.settings = load_settings()

        # Initialize query router with handlers (priority order)
        search_settings = self.settings.get("search", {})
        self.router = QueryRouter()
        self.router.register(SystemControlsHandler())   # 50: system controls
        self.router.register(CalculatorHandler())        # 100: math expressions
        self.router.register(WebSearchHandler())         # 200: web search
        self.router.register(CustomCommandsHandler())    # 300: custom commands
        self.router.register(AppSearchHandler(           # 1000: app search (fallback)
            max_results=search_settings.get("max_results", 30),
            fuzzy_threshold=search_settings.get("fuzzy_threshold", 50),
        ))

        # Current results from router
        self.current_results: list[ResultItem] = []
        self.current_handler = "app_search"

        # Widgets (created in create_window)
        self.search_entry = None
        self.results_box = None

        # Keyboard navigation
        self.selected_index = -1
        self.result_buttons = []

    def create_window(self):
        """
        Create the search panel window with slide animation.

        Returns:
            widgets.RevealerWindow positioned at top center
        """
        self.search_entry = widgets.Entry(
            placeholder_text="Search applications...",
            css_classes=["search-entry"],
            on_change=lambda x: self._on_search_changed()
        )
        self.search_entry.set_alignment(0.5)

        self.search_entry.connect("activate", lambda entry: self._on_entry_activate())

        self.results_box = widgets.Box(
            vertical=True,
            spacing=2,
            css_classes=["search-results"]
        )

        # Initial population
        self._on_search_changed()

        # Panel content
        content = widgets.Box(
            vertical=True,
            vexpand=True,
            valign="center",
            child=[
                widgets.Box(
                    vertical=True,
                    css_classes=["panel", "search-panel"],
                    child=[
                        self.search_entry,
                        widgets.Scroll(
                            hexpand=True,
                            max_content_height=500,
                            propagate_natural_height=True,
                            child=self.results_box
                        )
                    ]
                )
            ]
        )

        # Revealer for slide-down animation
        anim_duration = self.settings.get("animation", {}).get("transition_duration", 200)
        revealer = widgets.Revealer(
            transition_type="slide_down",
            transition_duration=anim_duration,
            reveal_child=True,
            child=content,
        )

        # Box wrapper required by RevealerWindow
        revealer_box = widgets.Box(child=[revealer])

        window = widgets.RevealerWindow(
            revealer=revealer,
            namespace="ignomi-search",
            css_classes=["ignomi-window"],
            monitor=get_monitor_under_cursor(),
            anchor=["top", "bottom"],
            exclusivity="normal",
            kb_mode="on_demand",
            layer="top",
            default_width=600,
            visible=False,
            margin_top=8,
            margin_bottom=8,
            child=revealer_box,
        )

        # Keyboard controller in CAPTURE phase to intercept arrows
        key_controller = Gtk.EventControllerKey()
        key_controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        key_controller.connect("key-pressed", self._on_key_press)
        window.add_controller(key_controller)

        window.connect("notify::visible", self._on_visibility_changed)

        return window

    def _on_search_changed(self):
        """Route query through handlers and update results."""
        query = self.search_entry.text if self.search_entry else ""
        self.current_handler, self.current_results = self.router.route(query)
        self.selected_index = -1
        self._update_results()

    def _update_results(self):
        """Rebuild results list from current ResultItem list."""
        clear_container(self.results_box)
        self.result_buttons = []

        for result in self.current_results:
            if result.widget_builder:
                # Custom widget (controls, calculator display, etc.)
                widget = result.widget_builder()
                self.results_box.append(widget)
                self.result_buttons.append(widget)
            else:
                button = self._create_result_button(result)
                self.results_box.append(button)
                self.result_buttons.append(button)

        if self.result_buttons:
            self.selected_index = 0
        else:
            self.selected_index = -1

        self._update_selection_highlight()

    def _create_result_button(self, result: ResultItem):
        """
        Create a button for a search result.

        Renders differently based on result_type:
        - "app": icon + name + description (center-aligned)
        - others: icon + title + description (center-aligned)
        """
        button = widgets.Button(
            can_focus=False,
            css_classes=["app-item", "result-item", f"result-{result.result_type}"],
            child=widgets.Box(
                halign="center",
                child=[
                    widgets.Box(
                        vertical=True,
                        spacing=4,
                        child=[
                            widgets.Box(
                                spacing=8,
                                halign="center",
                                valign="center",
                                child=[
                                    widgets.Icon(
                                        image=result.icon,
                                        pixel_size=24,
                                        css_classes=["app-icon"],
                                    ),
                                    widgets.Label(
                                        label=result.title,
                                        css_classes=["app-name", "search-app-name"],
                                        ellipsize="end",
                                        max_width_chars=35,
                                    ),
                                ],
                            ),
                            widgets.Label(
                                label=result.description,
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

        # Left-click: activate result
        gesture_left = Gtk.GestureClick()
        gesture_left.set_button(1)
        gesture_left.connect("pressed", lambda g, n, x, y, r=result: self._activate_result(r))
        button.add_controller(gesture_left)

        # Right-click: add to bookmarks (only for app results)
        if result.result_type == "app" and result.app:
            gesture_right = Gtk.GestureClick()
            gesture_right.set_button(3)
            gesture_right.connect(
                "pressed",
                lambda g, n, x, y, r=result, btn=button: add_bookmark_with_refresh(r.app.id, btn)
            )
            button.add_controller(gesture_right)

        return button

    def _activate_result(self, result: ResultItem):
        """Activate a result item — launch app or call custom handler."""
        if result.on_activate:
            result.on_activate()
        elif result.app:
            close_delay = self.settings["launcher"]["close_delay_ms"]
            launch_app(result.app, self.frecency, close_delay)

    def _on_visibility_changed(self, window, param):
        """Handle visibility changes - clear search on close, grab focus on open."""
        if window.get_visible():
            update_window_monitor(window)

            if self.result_buttons:
                self.selected_index = 0
                self._update_selection_highlight()

            GLib.timeout_add(300, self._grab_entry_focus)
        else:
            self.search_entry.set_text("")
            self.selected_index = -1

    def _grab_entry_focus(self):
        """
        Move cursor to search entry to ensure focus.

        Uses HyprlandService IPC instead of subprocess calls.
        """
        from ignis.services.hyprland import HyprlandService

        try:
            hyprland = HyprlandService.get_default()
            ignis_monitor_idx = get_monitor_under_cursor()

            from gi.repository import Gdk as _Gdk
            display = _Gdk.Display.get_default()
            if display:
                gtk_monitors = display.get_monitors()
                if ignis_monitor_idx < gtk_monitors.get_n_items():
                    gtk_monitor = gtk_monitors.get_item(ignis_monitor_idx)
                    connector = gtk_monitor.get_connector()

                    monitor = hyprland.get_monitor_by_name(connector)
                    if monitor:
                        window_x = monitor.x + (monitor.width - 600) // 2
                        window_y = monitor.y + 8

                        entry_x = window_x + 300
                        entry_y = window_y + 92

                        hyprland.send_command(
                            f"dispatch movecursor {entry_x} {entry_y}"
                        )

                        self.search_entry.grab_focus()
        except Exception:
            self.search_entry.grab_focus()

        return False

    def _on_entry_activate(self):
        """Handle Enter key press — activate selected result."""
        if 0 <= self.selected_index < len(self.current_results):
            self._activate_result(self.current_results[self.selected_index])

    def _on_key_press(self, controller, keyval, keycode, state):
        """Handle keyboard events in CAPTURE phase."""
        from utils.helpers import close_launcher

        if keyval == Gdk.KEY_Escape:
            close_launcher()
            return True

        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            if 0 <= self.selected_index < len(self.current_results):
                self._activate_result(self.current_results[self.selected_index])
                return True

        if not self.result_buttons:
            return False

        if keyval == Gdk.KEY_Down:
            if self.selected_index < len(self.result_buttons) - 1:
                self.selected_index += 1
                self._update_selection_highlight()
                self._scroll_to_selected()
            self.search_entry.grab_focus()
            return True

        elif keyval == Gdk.KEY_Up:
            if self.selected_index > 0:
                self.selected_index -= 1
                self._update_selection_highlight()
                self._scroll_to_selected()
            self.search_entry.grab_focus()
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
        # Visual selection is CSS-only; focus stays on search entry
        pass
