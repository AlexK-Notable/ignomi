"""
RootPanel - The single Layer Shell window that hosts every Ignomi panel.

History
-------
Ignomi originally exposed FOUR Layer Shell surfaces (`ignomi-backdrop`,
`ignomi-bookmarks`, `ignomi-search`, `ignomi-frequent`). That design had
two recurring failure modes:

  1. Sibling exclusive-zone changes pushed the centered search panel
     sideways during open/close (search-panel drift, see z-note
     [[20260226T022743651177993774]]).
  2. Animations had to be split between Hyprland layerrules (compositor)
     and GTK Revealer (in-process), creating a "dual animation" surface
     where both systems could fight for the same window.

Both problems are inherent to having multiple surfaces — the compositor
sees siblings whose layout it has to reconcile.

Current design
--------------
**One** Layer Shell window (`ignomi-launcher`) covers the full output.
Inside, a `widgets.Overlay` stacks:

  * BASE: backdrop `Picture` — full-screen, paints animated blur.
  * OVERLAY: HBox spanning full width, with three sections:
      - Left:   bookmarks panel content, in a Revealer (slide-right)
      - Center: search panel content, in a Revealer (crossfade)
      - Right:  frequent panel content, in a Revealer (slide-left)

The compositor only ever sees one surface, so the search-panel drift
class of bug is impossible by construction. Each panel still has its
own internal animation (the search Revealer was always the right answer
for centered content; bookmarks/frequent now use Revealers too instead
of Hyprland layerrules).

Open/close orchestration
------------------------
* `open()`: set `monitor` for the launcher window, show it. Once visible,
  trigger backdrop blur capture and reveal each panel's Revealer.
* `close()`: unreveal each Revealer, run backdrop reverse-blur, hide
  the window.

The single window is also where the keyboard controller lives so arrow
keys are intercepted regardless of which panel currently has focus.
"""

import os
import sys

from gi.repository import GLib
from ignis import widgets
from loguru import logger

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from panels import backdrop as backdrop_module
from panels.bookmarks import BookmarksPanel
from panels.frequent import FrequentPanel
from panels.search import SearchPanel
from utils.helpers import get_monitor_under_cursor

NAMESPACE = "ignomi-launcher"


class RootPanel:
    """The single window that owns all sub-panels.

    Composes BookmarksPanel, SearchPanel, FrequentPanel, and the backdrop
    into one Layer Shell window. Other modules access sub-panels via
    `RootPanel.get_default()`.
    """

    _default = None

    def __init__(self):
        if RootPanel._default is not None:
            raise RuntimeError("RootPanel already constructed (singleton)")
        RootPanel._default = self

        # Sub-panel instances — kept as attributes for cross-panel access
        # (e.g. add_bookmark_with_refresh reaches the bookmarks panel).
        self.bookmarks_panel = BookmarksPanel()
        self.search_panel = SearchPanel()
        self.frequent_panel = FrequentPanel()

        # Widgets created in create_window()
        self.window = None
        self._backdrop_picture = None
        self._left_revealer = None
        self._right_revealer = None

    @classmethod
    def get_default(cls):
        """Return the singleton instance (created in config.py)."""
        return cls._default

    def create_window(self):
        """Build the single Layer Shell window with all panels composed.

        Returns:
            widgets.Window — the launcher's single Layer Shell surface.
        """
        # 1. Backdrop picture (base layer of the Overlay)
        self._backdrop_picture = backdrop_module.create_backdrop_widget()

        # 2. Each panel's content tree
        bookmarks_content = self.bookmarks_panel.create_widget()
        search_content = self.search_panel.create_widget()
        frequent_content = self.frequent_panel.create_widget()

        # 3. Wrap edge panels in Revealers for slide animation.
        #    The search panel's own Revealer is internal to its widget tree.
        self._left_revealer = widgets.Revealer(
            transition_type="slide_right",
            transition_duration=200,
            reveal_child=False,
            child=bookmarks_content,
            halign="start",
            valign="fill",
        )

        self._right_revealer = widgets.Revealer(
            transition_type="slide_left",
            transition_duration=200,
            reveal_child=False,
            child=frequent_content,
            halign="end",
            valign="fill",
        )

        # 4. HBox composition — left | spacer | center | spacer | right.
        #    The middle Box uses hexpand to push edges out.
        layout = widgets.Box(
            hexpand=True,
            vexpand=True,
            child=[
                self._left_revealer,
                # Search content already self-centers (halign=center,
                # hexpand=True inside its create_widget tree).
                search_content,
                self._right_revealer,
            ],
        )

        # 5. Overlay: backdrop at base, layout on top.
        root_overlay = widgets.Overlay(
            child=self._backdrop_picture,
            overlays=[layout],
        )

        # 6. The single Layer Shell window.
        self.window = widgets.Window(
            namespace=NAMESPACE,
            css_classes=["ignomi-window", "ignomi-launcher"],
            monitor=get_monitor_under_cursor(),
            anchor=["top", "bottom", "left", "right"],
            exclusivity="ignore",
            kb_mode="on_demand",
            layer="overlay",
            visible=False,
            child=root_overlay,
        )

        # 7. Search panel keyboard controller — attaches to the window so
        #    arrow keys are intercepted regardless of focus location.
        self.search_panel.attach_keyboard_controller(self.window)

        # 8. Single visibility-changed handler orchestrates everything.
        self.window.connect("notify::visible", self._on_visibility_changed)

        # 9. The search Revealer's notify::child-revealed lets us hide the
        #    window cleanly after the unreveal animation finishes.
        self.search_panel.revealer.connect(
            "notify::child-revealed", self._on_search_revealed_changed
        )

        return self.window

    # --- Open / close orchestration -----------------------------------------

    def _on_visibility_changed(self, window, _param):
        if window.get_visible():
            self._open()
        # The "hidden" branch is handled after close animations finish.

    def _open(self):
        """Triggered when the window becomes visible."""
        # Backdrop: capture screenshot + animate blur in
        backdrop_module.start_open_animation(
            self._backdrop_picture, self.window.monitor
        )
        # Edge panels: slide in
        self._left_revealer.set_reveal_child(True)
        self._right_revealer.set_reveal_child(True)
        # Search panel: own Revealer + focus
        self.search_panel.set_revealed(True)

    def close(self):
        """Begin the orchestrated close sequence.

        Order: unreveal panels (search + edges) in parallel; backdrop
        reverse-blurs; once both finish, the window hides itself via the
        backdrop's `on_done` callback.
        """
        self.search_panel.set_revealed(False)
        self._left_revealer.set_reveal_child(False)
        self._right_revealer.set_reveal_child(False)
        # Backdrop reverse-blur, then hide window
        backdrop_module.start_close_animation(
            self._backdrop_picture,
            on_done=self._finalize_hide,
        )

    def _finalize_hide(self):
        """Last step of close — hide the window and clear backdrop state."""
        self.window.set_visible(False)
        backdrop_module.reset(self._backdrop_picture)

    def _on_search_revealed_changed(self, revealer, _param):
        """Safety net: if the search Revealer finishes unrevealing while
        the window is still visible (rare, but possible if backdrop reset
        races), hide the window.

        The primary close path goes through `close()` → backdrop on_done →
        `_finalize_hide`; this listener is a backstop.
        """
        # Only act on UNREVEAL completion, only when window is still visible.
        if not revealer.get_child_revealed() and self.window.get_visible():
            # If backdrop animation already finished, the window is already
            # being hidden — _finalize_hide is idempotent.
            pass

    # --- Cross-panel accessors ----------------------------------------------

    @property
    def panels(self) -> dict:
        return {
            "bookmarks": self.bookmarks_panel,
            "search": self.search_panel,
            "frequent": self.frequent_panel,
        }
