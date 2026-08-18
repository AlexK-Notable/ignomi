"""
Screen Manager - Swaps whole "screens" inside the single launcher window.

Motivation
----------
Ignomi has exactly ONE Layer Shell surface (`ignomi-launcher`, see
panels/root.py). Everything the user sees is composed inside it. Until
now that composition was fixed: bookmarks | search | frequent, forever.

A *screen* is a full-window content tree that can replace that default
composition. Pressing a nav button swaps the home screen out and the
target screen in; Escape swaps back. This is the generic mechanism
behind "a button leads to a new panel space" — adding another one is
three lines (write the screen, register it, done), not a refactor.

Design constraints
------------------
1. **Screen switching is a Stack crossfade and NOTHING else.** The
   panel Revealers (slide-right / slide-left / crossfade) are driven
   ONLY by launcher open/close. Never by screen switching. Animating
   both at once is the dual-animation conflict this codebase has scar
   tissue about (z-note [[20260225T072152714557306660]]); keeping the
   two concerns on separate widgets makes it impossible by construction.

2. **Mechanism here, policy in RootPanel.** This class knows how to
   register, build and switch. It does not decide what Escape means —
   RootPanel owns that, because "Escape goes back, unless you're home,
   then it closes" is launcher policy, not stack mechanics.

3. **Structural typing, no inheritance** — same convention as
   `SearchHandler` in search/router.py. A screen is anything with the
   right attributes. Optional hooks are probed with `getattr`, so a
   minimal screen only needs `name`, `title`, `icon` and
   `create_widget()`.

Ignis quirk worth knowing
-------------------------
`widgets.Stack`'s `child` setter calls ``add_titled(child, None, title)``
— it passes ``name=None``, so stack pages have NO name and
``set_visible_child_name()`` can never work. We therefore keep our own
``name -> widget`` map and switch with ``set_visible_child(widget)``.
"""

from typing import Protocol

from loguru import logger

from ignis import widgets


class Screen(Protocol):
    """Structural type for a launcher screen. No inheritance required.

    Required attributes:
        name:  unique key used by `switch_to()`.
        title: human-readable label, shown on the nav button.
        icon:  GTK icon name, shown on the nav button.

    Required method:
        create_widget(): build and return the screen's content tree.

    Optional hooks (probed with getattr, omit them freely):
        show_in_nav (bool):  generate a nav button for this screen.
                             Defaults to True when absent.
        on_enter():          called after this screen becomes visible.
        on_leave():          called before this screen is replaced.
        on_key_press(keyval, state) -> bool:
                             screen-local key handling. Return True to
                             consume the event.
    """

    name: str
    title: str
    icon: str

    def create_widget(self): ...


class ScreenManager:
    """Registry + Stack for the launcher's screens.

    Typical wiring (see panels/root.py)::

        screens = ScreenManager(transition_duration=200)
        screens.register(HomeScreen(screens), is_home=True)
        screens.register(SystemdScreen())
        stack = screens.build()
    """

    def __init__(self, transition_duration: int = 200):
        self._screens: dict[str, Screen] = {}
        self._order: list[str] = []
        self._widgets: dict[str, object] = {}
        self._home: str | None = None
        self._current: str | None = None
        self._stack = None
        self._transition_duration = transition_duration

    # --- Registration -------------------------------------------------------

    def register(self, screen, *, is_home: bool = False) -> None:
        """Register a screen.

        Args:
            screen:  any object satisfying the `Screen` protocol.
            is_home: mark this as the screen the launcher opens on and
                     that `go_home()` returns to. Exactly one screen
                     should set this.

        Raises:
            ValueError: on a duplicate name, or a second home screen.
        """
        name = screen.name
        if name in self._screens:
            raise ValueError(f"Screen '{name}' already registered")

        if is_home:
            if self._home is not None:
                raise ValueError(
                    f"Home screen already set to '{self._home}'; "
                    f"'{name}' cannot also be home"
                )
            self._home = name

        self._screens[name] = screen
        self._order.append(name)
        logger.debug(f"[screens] registered '{name}' (home={is_home})")

    # --- Construction -------------------------------------------------------

    def build(self):
        """Build the Stack containing every registered screen.

        Must be called AFTER all `register()` calls — screens are free
        to inspect the registry inside `create_widget()` (HomeScreen
        builds its nav bar that way).

        Returns:
            widgets.Stack — with the home screen visible.

        Raises:
            RuntimeError: if no home screen was registered.
        """
        if self._home is None:
            raise RuntimeError("No home screen registered; pass is_home=True")

        pages = []
        for name in self._order:
            screen = self._screens[name]
            widget = screen.create_widget()
            self._widgets[name] = widget
            pages.append(widgets.StackPage(title=name, child=widget))

        self._stack = widgets.Stack(
            transition_type="crossfade",
            transition_duration=self._transition_duration,
            hexpand=True,
            vexpand=True,
            child=pages,
        )

        # Open on home. Set _current directly rather than via switch_to()
        # so we don't fire on_enter() before the window is even visible.
        self._current = self._home
        self._stack.set_visible_child(self._widgets[self._home])

        return self._stack

    # --- Switching ----------------------------------------------------------

    def switch_to(self, name: str) -> bool:
        """Make `name` the visible screen.

        Fires `on_leave()` on the outgoing screen and `on_enter()` on the
        incoming one, both optional and both failure-isolated: a screen
        that raises in a lifecycle hook must not strand the user on a
        half-switched launcher.

        Args:
            name: registered screen name.

        Returns:
            True if the screen changed, False if unknown, not yet built,
            or already current.
        """
        if self._stack is None:
            logger.warning(f"[screens] switch_to('{name}') before build()")
            return False
        if name not in self._screens:
            logger.warning(f"[screens] unknown screen '{name}'")
            return False
        if name == self._current:
            return False

        outgoing = self._screens.get(self._current) if self._current else None
        if outgoing is not None:
            self._safe_hook(outgoing, "on_leave")

        self._current = name
        self._stack.set_visible_child(self._widgets[name])
        logger.debug(f"[screens] -> {name}")

        self._safe_hook(self._screens[name], "on_enter")
        return True

    def go_home(self) -> bool:
        """Switch back to the home screen. No-op if already there."""
        if self._home is None:
            return False
        return self.switch_to(self._home)

    @staticmethod
    def _safe_hook(screen, hook_name: str) -> None:
        """Call an optional lifecycle hook, swallowing and logging errors."""
        hook = getattr(screen, hook_name, None)
        if hook is None:
            return
        try:
            hook()
        except Exception:
            logger.exception(
                f"[screens] {hook_name}() raised on "
                f"'{getattr(screen, 'name', '?')}'"
            )

    # --- Key routing --------------------------------------------------------

    def handle_key(self, keyval, state) -> bool:
        """Offer a key event to the active screen.

        RootPanel calls this from the window-level CAPTURE controller
        after applying its own global policy (Escape). Screens without
        an `on_key_press` simply decline.

        Returns:
            True if the active screen consumed the event.
        """
        screen = self.current_screen
        if screen is None:
            return False
        handler = getattr(screen, "on_key_press", None)
        if handler is None:
            return False
        try:
            return bool(handler(keyval, state))
        except Exception:
            logger.exception(
                f"[screens] on_key_press() raised on '{screen.name}'"
            )
            return False

    # --- Accessors ----------------------------------------------------------

    @property
    def current(self) -> str | None:
        """Name of the visible screen."""
        return self._current

    @property
    def current_screen(self):
        """The visible screen object, or None before build()."""
        if self._current is None:
            return None
        return self._screens.get(self._current)

    @property
    def home_name(self) -> str | None:
        """Name of the registered home screen."""
        return self._home

    @property
    def is_home(self) -> bool:
        """True when the home screen is visible."""
        return self._current is not None and self._current == self._home

    @property
    def stack(self):
        """The Stack widget, or None before build()."""
        return self._stack

    def get(self, name: str):
        """Look up a registered screen by name."""
        return self._screens.get(name)

    def nav_screens(self) -> list:
        """Screens that should get a nav button, in registration order.

        The home screen is always excluded — you don't navigate to the
        place the button lives. Any screen may opt out with
        `show_in_nav = False`.
        """
        return [
            self._screens[name]
            for name in self._order
            if name != self._home
            and getattr(self._screens[name], "show_in_nav", True)
        ]
