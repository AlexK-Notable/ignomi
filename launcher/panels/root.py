"""
RootPanel - The single Layer Shell window that hosts every Ignomi screen.

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

  * BASE:    backdrop `Picture` — full-screen, paints animated blur.
  * OVERLAY: the screen `Stack` (see screens/manager.py).

A *screen* is a full-window content tree. `HomeScreen` is the default
one and holds what used to be composed inline here — bookmarks left,
search centre, frequent right — plus a nav bar. `SystemdScreen` is
reached by pressing its nav button; Escape returns home.

RootPanel now owns three things and delegates the rest:

  * the window and the backdrop,
  * open/close orchestration (which it hands to the home screen), and
  * **global key policy** — specifically what Escape means. Everything
    else is offered to the active screen.

Why Escape is policy here and not in a panel
--------------------------------------------
The CAPTURE-phase key controller sits on the window, so it sees every
keystroke before any panel does. It used to belong to SearchPanel, which
unconditionally closed the launcher on Escape — correct when there was
only one screen, wrong the moment there are two. "Escape goes back,
unless you are already home, in which case it closes" is a property of
the launcher, so the launcher owns it.

Open/close orchestration
------------------------
* `open()`: set `monitor`, show the window. Once visible, trigger the
  backdrop blur capture and reveal the home screen's panels.
* `close()`: unreveal, run the backdrop reverse-blur, hide the window,
  then reset to the home screen so the next open is predictable.
"""

import os
import sys

from gi.repository import Gdk, Gtk

from ignis import widgets

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from panels import backdrop as backdrop_module
from screens.manager import ScreenManager
from utils.helpers import get_monitor_under_cursor, load_settings

# NOTE: HomeScreen and SystemdScreen are imported lazily inside
# `__init__`, NOT here. HomeScreen imports the three panel classes, which
# runs `panels/__init__.py`, which imports this module — a cycle. Whether
# it blows up depends on which package gets imported first, so it would
# have been an intermittent, import-order-dependent failure (it surfaced
# as one: `pytest tests/test_screens.py` broke while `ignis init` was
# fine). Deferring to call time removes the cycle for every order.
# `screens.manager` is safe at module level: it imports nothing local.

NAMESPACE = "ignomi-launcher"


class RootPanel:
    """The single window that owns the backdrop and every screen."""

    _default = None

    def __init__(self):
        if RootPanel._default is not None:
            raise RuntimeError("RootPanel already constructed (singleton)")
        RootPanel._default = self

        # Deferred to break the panels <-> screens import cycle (see the
        # note beside the module-level imports).
        from screens.home import HomeScreen
        from screens.systemd import SystemdScreen

        settings = load_settings()
        duration = settings.get("animation", {}).get("transition_duration", 200)

        # --- Screen registry ------------------------------------------------
        # Registration order is nav-bar order. To add a screen: write it,
        # register it here, done — the nav button is generated for you.
        self.screens = ScreenManager(transition_duration=duration)
        self.home_screen = HomeScreen(self.screens, transition_duration=duration)
        self.screens.register(self.home_screen, is_home=True)
        self.screens.register(SystemdScreen())

        # Widgets created in create_window()
        self.window = None
        self._backdrop_picture = None

    @classmethod
    def get_default(cls):
        """Return the singleton instance (created in config.py)."""
        return cls._default

    def create_window(self):
        """Build the single Layer Shell window with every screen composed.

        Returns:
            widgets.Window — the launcher's single Layer Shell surface.
        """
        # 1. Backdrop picture (base layer of the Overlay)
        self._backdrop_picture = backdrop_module.create_backdrop_widget()

        # 2. The screen Stack. build() calls create_widget() on each
        #    registered screen, so it must come after registration.
        screen_stack = self.screens.build()

        # 3. Overlay: backdrop at base, screens on top.
        root_overlay = widgets.Overlay(
            child=self._backdrop_picture,
            overlays=[screen_stack],
        )

        # 4. The single Layer Shell window.
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

        # 5. Window-level CAPTURE key controller. On the WINDOW, not on a
        #    panel, so it fires regardless of which widget has focus.
        self._attach_keyboard_controller()

        # 6. Single visibility-changed handler orchestrates open.
        self.window.connect("notify::visible", self._on_visibility_changed)

        return self.window

    # --- Keyboard routing ---------------------------------------------------

    def _attach_keyboard_controller(self):
        """Wire the CAPTURE-phase key controller to the launcher window."""
        controller = Gtk.EventControllerKey()
        controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        controller.connect("key-pressed", self._on_key_press)
        self.window.add_controller(controller)

    def _on_key_press(self, controller, keyval, keycode, state):
        """Global policy first, then the active screen.

        Escape is the only key handled globally: it backs out one level,
        closing the launcher only when there is no level left to back out
        of. Every other key is offered to the current screen.
        """
        if keyval == Gdk.KEY_Escape:
            if not self.screens.is_home:
                self.screens.go_home()
            else:
                from utils.helpers import close_launcher

                close_launcher()
            return True

        return self.screens.handle_key(keyval, state)

    # --- Open / close orchestration -----------------------------------------

    def _on_visibility_changed(self, window, _param):
        if window.get_visible():
            self._open()
        # The "hidden" branch is handled after close animations finish.

    def _open(self):
        """Triggered when the window becomes visible."""
        # Defensive: close() resets to home, but if a close was
        # interrupted we could still be on another screen. Idempotent.
        self.screens.go_home()

        # Backdrop: capture screenshot + animate blur in
        backdrop_module.start_open_animation(
            self._backdrop_picture, self.window.monitor
        )
        # Home screen: slide/fade its panels in and focus the search entry
        self.home_screen.set_revealed(True)

    def close(self):
        """Begin the orchestrated close sequence.

        Order: unreveal the home screen's panels in parallel; backdrop
        reverse-blurs; once it finishes, the window hides itself via the
        backdrop's `on_done` callback.
        """
        self.home_screen.set_revealed(False)
        backdrop_module.start_close_animation(
            self._backdrop_picture,
            on_done=self._finalize_hide,
        )

    def _finalize_hide(self):
        """Last step of close — hide the window and reset state.

        Resetting to home happens HERE, after the window is already
        invisible, so the user never sees the screen crossfade back.
        """
        self.window.set_visible(False)
        backdrop_module.reset(self._backdrop_picture)
        self.screens.go_home()

    # --- Cross-panel accessors ----------------------------------------------
    #
    # The home screen owns the three original panels now. These
    # properties preserve the pre-screens contract — `utils.helpers`
    # reaches `RootPanel.get_default().bookmarks_panel`, and callers
    # should not have to know about screens to do that.

    @property
    def bookmarks_panel(self):
        return self.home_screen.bookmarks_panel

    @property
    def search_panel(self):
        return self.home_screen.search_panel

    @property
    def frequent_panel(self):
        return self.home_screen.frequent_panel

    @property
    def panels(self) -> dict:
        return {
            "bookmarks": self.bookmarks_panel,
            "search": self.search_panel,
            "frequent": self.frequent_panel,
        }
