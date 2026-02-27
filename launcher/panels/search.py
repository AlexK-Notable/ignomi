"""
Search Panel - Center panel with search entry and filtered results.

Features:
- Query router dispatches to typed handlers (app search, calculator, etc.)
- Real-time filtering with debounced input
- Keyboard navigation with scroll-to-selected
- Right-click to add apps to bookmarks
- Auto-focus search field when launcher opens
- Clear search term when launcher closes (with close guard)
"""

import os
import sys

from gi.repository import Gdk, GLib, Gtk
from ignis.services.applications import ApplicationsService

from ignis import widgets

# Add launcher directory to path dynamically (works from any location/worktree)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from search.handlers import (
    AppSearchHandler,
    CalculatorHandler,
    CustomCommandsHandler,
    SystemControlsHandler,
    WebSearchHandler,
)
from search.router import QueryRouter, ResultItem
from services.frecency import get_frecency_service
from utils.helpers import (
    add_bookmark_with_refresh,
    get_monitor_under_cursor,
    launch_app,
    load_settings,
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
        self._revealer = None

        # Debounce and close guard
        self._debounce_timer = None
        self._closing = False

    def create_window(self):
        """
        Create the search panel window.

        The search panel uses a GTK Revealer for open/close animation
        (crossfade). Edge-anchored panels (bookmarks, frequent) use
        Hyprland layerrules, but the centered search panel drifts
        laterally with compositor slide animations — GTK Revealer
        gives us full control.

        Returns:
            widgets.Window positioned at top center
        """
        self.search_entry = widgets.Entry(
            placeholder_text="Search applications...",
            css_classes=["search-entry"],
            on_change=lambda x: self._on_search_changed()
        )
        self.search_entry.set_alignment(0.5)

        self.search_entry.connect("activate", lambda entry: self._on_entry_activate())

        self.results_box = widgets.ListBox(
            css_classes=["search-results"],
        )

        # Initial population
        self._do_search()

        # Panel content (no vexpand/valign — Revealer controls sizing)
        panel_content = widgets.Box(
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

        # Revealer nested INSIDE the centering box so it clips within
        # the content's own height, not the full window height.
        self._revealer = widgets.Revealer(
            transition_type="crossfade",
            transition_duration=200,
            reveal_child=False,
            child=panel_content,
        )

        # Centering wrapper — stays centered regardless of Revealer state
        centered = widgets.Box(
            vertical=True,
            vexpand=True,
            valign="center",
            child=[self._revealer],
        )

        window = widgets.Window(
            namespace="ignomi-search",
            css_classes=["ignomi-window"],
            monitor=get_monitor_under_cursor(),
            anchor=["top", "bottom"],
            default_width=600,
            exclusivity="ignore",
            kb_mode="on_demand",
            layer="overlay",
            visible=False,
            margin_top=8,
            margin_bottom=8,
            child=centered,
        )

        # Keyboard controller in CAPTURE phase to intercept arrows
        key_controller = Gtk.EventControllerKey()
        key_controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        key_controller.connect("key-pressed", self._on_key_press)
        window.add_controller(key_controller)

        window.connect("notify::visible", self._on_visibility_changed)

        # Hide window the instant revealer animation completes (no lingering tail)
        self._revealer.connect("notify::child-revealed", self._on_child_revealed)

        return window

    def _on_child_revealed(self, revealer, param):
        """Hide window immediately when unreveal animation finishes."""
        if not revealer.get_child_revealed():
            window = revealer.get_root()
            if window:
                window.set_visible(False)

    def _on_search_changed(self):
        """Debounced search — waits 120ms after last keystroke."""
        if self._closing:
            return
        if self._debounce_timer is not None:
            GLib.source_remove(self._debounce_timer)
        self._debounce_timer = GLib.timeout_add(120, self._do_search)

    def _do_search(self):
        """Execute the actual search query (called after debounce)."""
        self._debounce_timer = None
        query = self.search_entry.text if self.search_entry else ""
        self.current_handler, self.current_results = self.router.route(query)
        self._update_results()
        return False  # Don't repeat GLib timeout

    def _update_results(self):
        """Rebuild results list from current ResultItem list."""
        self.results_box.remove_all()

        for result in self.current_results:
            if result.widget_builder:
                widget = result.widget_builder()
                row = widgets.ListBoxRow(child=widget)
                self.results_box.append(row)
            else:
                row = self._create_result_row(result)
                self.results_box.append(row)

        rows = self.results_box.rows
        if rows:
            self.results_box.select_row(rows[0])

    def _create_result_row(self, result: ResultItem):
        """Create a ListBoxRow for a search result."""
        row = widgets.ListBoxRow(
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
            on_activate=lambda r, result=result: self._activate_result(result),
        )

        # Right-click: add to bookmarks (only for app results)
        if result.result_type == "app" and result.app:
            gesture_right = Gtk.GestureClick()
            gesture_right.set_button(3)
            gesture_right.connect(
                "pressed",
                lambda g, n, x, y, r=result, rw=row: add_bookmark_with_refresh(r.app.id, rw)
            )
            row.add_controller(gesture_right)

        return row

    def _activate_result(self, result: ResultItem):
        """Activate a result item — launch app or call custom handler."""
        if result.on_activate:
            result.on_activate()
        elif result.app:
            close_delay = self.settings["launcher"]["close_delay_ms"]
            launch_app(result.app, self.frecency, close_delay)

    PANEL_WIDTH = 600

    def _on_visibility_changed(self, window, param):
        """Handle visibility changes — reveal on open, clear on close."""
        if window.get_visible():
            # Monitor set by toggle_launcher() before visibility

            # Reveal content with crossfade animation
            self._revealer.set_reveal_child(True)

            rows = self.results_box.rows
            if rows:
                self.results_box.select_row(rows[0])

            GLib.timeout_add(300, self._grab_entry_focus)
        else:
            # Close guard: prevent set_text("") from triggering a new search
            self._closing = True
            self.search_entry.set_text("")
            self._closing = False
            # Reset revealer for next open (window is already hidden)
            self._revealer.set_reveal_child(False)

    def _grab_entry_focus(self):
        """
        Move cursor to search entry to ensure focus.

        Uses HyprlandService IPC instead of subprocess calls.
        """
        try:
            from ignis.services.hyprland import HyprlandService
            from gi.repository import Gdk as _Gdk

            hyprland = HyprlandService.get_default()
            ignis_monitor_idx = get_monitor_under_cursor()
            display = _Gdk.Display.get_default()
            if display:
                gtk_monitors = display.get_monitors()
                if ignis_monitor_idx < gtk_monitors.get_n_items():
                    connector = gtk_monitors.get_item(ignis_monitor_idx).get_connector()
                    monitor = hyprland.get_monitor_by_name(connector)
                    if monitor:
                        entry_x = monitor.x + (monitor.width // 2)
                        entry_y = monitor.y + 100

                        hyprland.send_command(
                            f"dispatch movecursor {entry_x} {entry_y}"
                        )

            self.search_entry.grab_focus()
        except Exception:
            self.search_entry.grab_focus()

        return False

    def _on_entry_activate(self):
        """Handle Enter key press — activate selected result."""
        selected = self.results_box.get_selected_row()
        if selected:
            self.results_box.activate_row(selected)

    def _on_key_press(self, controller, keyval, keycode, state):
        """Handle keyboard events in CAPTURE phase."""
        from utils.helpers import close_launcher

        if keyval == Gdk.KEY_Escape:
            close_launcher()
            return True

        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            selected = self.results_box.get_selected_row()
            if selected:
                self.results_box.activate_row(selected)
            return True

        rows = self.results_box.rows
        if not rows:
            return False

        selected = self.results_box.get_selected_row()
        current_idx = selected.get_index() if selected else -1

        if keyval == Gdk.KEY_Down:
            if current_idx < len(rows) - 1:
                self.results_box.select_row(rows[current_idx + 1])
                self._ensure_visible()
            self.search_entry.grab_focus()
            return True

        elif keyval == Gdk.KEY_Up:
            if current_idx > 0:
                self.results_box.select_row(rows[current_idx - 1])
                self._ensure_visible()
            self.search_entry.grab_focus()
            return True

        return False

    def _ensure_visible(self):
        """Scroll to make selected row visible by briefly grabbing focus."""
        selected = self.results_box.get_selected_row()
        if selected:
            selected.grab_focus()
            if self.search_entry:
                self.search_entry.grab_focus()
