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
        self.router.register(WebSearchHandler(           # 200: web search
            engines=self.settings.get("web_search", {}).get("engines") or None,
        ))
        self.router.register(CustomCommandsHandler())    # 300: custom commands
        self.router.register(AppSearchHandler(           # 1000: app search (fallback)
            max_results=search_settings.get("max_results", 30),
            fuzzy_threshold=search_settings.get("fuzzy_threshold", 50),
            frecency_service=self.frecency,
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

    def create_widget(self):
        """
        Create the search panel widget tree wrapped in its own Revealer.

        Used by RootPanel to compose a single Layer Shell window. The
        Revealer (crossfade) is owned by the search panel itself because
        the centered surface needs an animation that is independent of
        the rest of the launcher (historical: see animation-architecture.md).

        Returns:
            widgets.Box — the centered search panel with its Revealer
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

        self._revealer = widgets.Revealer(
            transition_type="crossfade",
            transition_duration=200,
            reveal_child=False,
            child=panel_content,
        )

        # Centering wrapper — stays centered regardless of Revealer state.
        # halign+valign center this widget within the parent Overlay slot.
        return widgets.Box(
            vertical=True,
            vexpand=True,
            hexpand=True,
            halign="center",
            valign="center",
            margin_top=8,
            margin_bottom=8,
            child=[self._revealer],
        )

    def attach_keyboard_controller(self, window):
        """Wire the CAPTURE-phase keyboard controller to the root window.

        Called by RootPanel after constructing the single Layer Shell
        window. The controller is on the WINDOW (not the search widget)
        so arrow keys are intercepted regardless of which panel has focus.
        """
        key_controller = Gtk.EventControllerKey()
        key_controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        key_controller.connect("key-pressed", self._on_key_press)
        window.add_controller(key_controller)

    def set_revealed(self, revealed: bool):
        """RootPanel calls this when the launcher window opens/closes."""
        if revealed:
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
            self._revealer.set_reveal_child(False)

    @property
    def revealer(self):
        """Expose the Revealer so RootPanel can chain notify::child-revealed."""
        return self._revealer

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
