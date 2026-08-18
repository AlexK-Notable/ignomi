"""
Tests for ScreenManager — the reusable button-leads-to-a-new-panel-space
mechanism.

Uses stub screens rather than the real HomeScreen/SystemdScreen: this
file is about registry and switching semantics, and constructing the real
home screen would drag in three panels and a search router for no
benefit. `widgets.*` comes from the conftest fakes, so the Stack is a
MagicMock whose `set_visible_child` calls we can assert on.
"""

import pytest

from screens.manager import ScreenManager


class StubScreen:
    """Minimal screen: records lifecycle calls in order."""

    def __init__(self, name, title=None, show_in_nav=True, key_result=False):
        self.name = name
        self.title = title or name.title()
        self.icon = "application-x-executable"
        self.show_in_nav = show_in_nav
        self.calls = []
        self.widget = object()
        self._key_result = key_result

    def create_widget(self):
        self.calls.append("create_widget")
        return self.widget

    def on_enter(self):
        self.calls.append("on_enter")

    def on_leave(self):
        self.calls.append("on_leave")

    def on_key_press(self, keyval, state):
        self.calls.append(("on_key_press", keyval))
        return self._key_result


class BareScreen:
    """A screen with only the required surface — no optional hooks."""

    def __init__(self, name):
        self.name = name
        self.title = name
        self.icon = "x"

    def create_widget(self):
        return object()


# --- Registration -----------------------------------------------------------

def test_register_duplicate_name_raises():
    mgr = ScreenManager()
    mgr.register(StubScreen("home"), is_home=True)
    with pytest.raises(ValueError, match="already registered"):
        mgr.register(StubScreen("home"))


def test_second_home_screen_raises():
    mgr = ScreenManager()
    mgr.register(StubScreen("home"), is_home=True)
    with pytest.raises(ValueError, match="cannot also be home"):
        mgr.register(StubScreen("other"), is_home=True)


def test_build_without_home_raises():
    mgr = ScreenManager()
    mgr.register(StubScreen("systemd"))
    with pytest.raises(RuntimeError, match="No home screen"):
        mgr.build()


# --- Nav bar generation -----------------------------------------------------

def test_nav_screens_excludes_home():
    mgr = ScreenManager()
    home = StubScreen("home")
    systemd = StubScreen("systemd")
    mgr.register(home, is_home=True)
    mgr.register(systemd)

    assert mgr.nav_screens() == [systemd]


def test_nav_screens_respects_show_in_nav_opt_out():
    mgr = ScreenManager()
    mgr.register(StubScreen("home"), is_home=True)
    visible = StubScreen("systemd")
    hidden = StubScreen("secret", show_in_nav=False)
    mgr.register(visible)
    mgr.register(hidden)

    assert mgr.nav_screens() == [visible]


def test_nav_screens_preserves_registration_order():
    mgr = ScreenManager()
    mgr.register(StubScreen("home"), is_home=True)
    first = StubScreen("aaa")
    second = StubScreen("zzz")
    third = StubScreen("mmm")
    for screen in (first, second, third):
        mgr.register(screen)

    # Registration order, NOT alphabetical — the config author controls
    # button order by ordering their register() calls.
    assert mgr.nav_screens() == [first, second, third]


def test_bare_screen_defaults_to_showing_in_nav():
    """A screen omitting show_in_nav still gets a button."""
    mgr = ScreenManager()
    mgr.register(StubScreen("home"), is_home=True)
    bare = BareScreen("minimal")
    mgr.register(bare)

    assert mgr.nav_screens() == [bare]


# --- Build ------------------------------------------------------------------

def test_build_starts_on_home_without_firing_on_enter():
    """on_enter must not fire at build time — the window isn't visible yet."""
    mgr = ScreenManager()
    home = StubScreen("home")
    mgr.register(home, is_home=True)
    mgr.register(StubScreen("systemd"))
    mgr.build()

    assert mgr.current == "home"
    assert mgr.is_home is True
    assert "on_enter" not in home.calls


def test_build_creates_widget_for_every_screen():
    mgr = ScreenManager()
    home = StubScreen("home")
    systemd = StubScreen("systemd")
    mgr.register(home, is_home=True)
    mgr.register(systemd)
    mgr.build()

    assert home.calls.count("create_widget") == 1
    assert systemd.calls.count("create_widget") == 1


# --- Switching --------------------------------------------------------------

def test_switch_to_fires_leave_then_enter():
    mgr = ScreenManager()
    home = StubScreen("home")
    systemd = StubScreen("systemd")
    mgr.register(home, is_home=True)
    mgr.register(systemd)
    mgr.build()

    assert mgr.switch_to("systemd") is True
    assert mgr.current == "systemd"
    assert mgr.is_home is False
    assert home.calls[-1] == "on_leave"
    assert systemd.calls[-1] == "on_enter"


def test_switch_to_sets_visible_child_by_widget_not_name():
    """Ignis' Stack pages have no name, so switching must use the widget.

    Guards the quirk documented in screens/manager.py: the `child` setter
    calls add_titled(child, None, title), so set_visible_child_name()
    could never work.
    """
    mgr = ScreenManager()
    home = StubScreen("home")
    systemd = StubScreen("systemd")
    mgr.register(home, is_home=True)
    mgr.register(systemd)
    stack = mgr.build()

    mgr.switch_to("systemd")

    stack.set_visible_child.assert_called_with(systemd.widget)
    assert stack.set_visible_child_name.call_count == 0


def test_switch_to_unknown_screen_is_refused():
    mgr = ScreenManager()
    home = StubScreen("home")
    mgr.register(home, is_home=True)
    mgr.build()

    assert mgr.switch_to("nope") is False
    assert mgr.current == "home"
    assert "on_leave" not in home.calls


def test_switch_to_current_screen_is_a_noop():
    """Re-pressing a nav button must not re-fire lifecycle hooks."""
    mgr = ScreenManager()
    home = StubScreen("home")
    systemd = StubScreen("systemd")
    mgr.register(home, is_home=True)
    mgr.register(systemd)
    mgr.build()
    mgr.switch_to("systemd")
    enter_count = systemd.calls.count("on_enter")

    assert mgr.switch_to("systemd") is False
    assert systemd.calls.count("on_enter") == enter_count


def test_switch_to_before_build_is_refused():
    mgr = ScreenManager()
    mgr.register(StubScreen("home"), is_home=True)
    mgr.register(StubScreen("systemd"))

    assert mgr.switch_to("systemd") is False


def test_go_home_returns_to_home():
    mgr = ScreenManager()
    home = StubScreen("home")
    systemd = StubScreen("systemd")
    mgr.register(home, is_home=True)
    mgr.register(systemd)
    mgr.build()
    mgr.switch_to("systemd")

    assert mgr.go_home() is True
    assert mgr.current == "home"
    assert systemd.calls[-1] == "on_leave"
    assert home.calls[-1] == "on_enter"


def test_go_home_when_already_home_is_a_noop():
    """RootPanel calls go_home() defensively on open; it must be free."""
    mgr = ScreenManager()
    home = StubScreen("home")
    mgr.register(home, is_home=True)
    mgr.build()

    assert mgr.go_home() is False
    assert home.calls.count("on_enter") == 0


# --- Failure isolation ------------------------------------------------------

def test_screen_raising_in_on_enter_does_not_strand_the_switch():
    """A broken screen must not leave the launcher half-switched."""
    class Exploding(StubScreen):
        def on_enter(self):
            raise RuntimeError("boom")

    mgr = ScreenManager()
    mgr.register(StubScreen("home"), is_home=True)
    mgr.register(Exploding("systemd"))
    mgr.build()

    assert mgr.switch_to("systemd") is True
    assert mgr.current == "systemd"


def test_screen_raising_in_on_leave_does_not_block_switching_away():
    class Exploding(StubScreen):
        def on_leave(self):
            raise RuntimeError("boom")

    mgr = ScreenManager()
    mgr.register(Exploding("home"), is_home=True)
    mgr.register(StubScreen("systemd"))
    mgr.build()

    assert mgr.switch_to("systemd") is True
    assert mgr.current == "systemd"


def test_bare_screen_without_hooks_switches_cleanly():
    mgr = ScreenManager()
    mgr.register(StubScreen("home"), is_home=True)
    mgr.register(BareScreen("minimal"))
    mgr.build()

    assert mgr.switch_to("minimal") is True
    assert mgr.current == "minimal"


# --- Key routing ------------------------------------------------------------

def test_handle_key_delegates_to_active_screen():
    mgr = ScreenManager()
    home = StubScreen("home", key_result=True)
    mgr.register(home, is_home=True)
    mgr.build()

    assert mgr.handle_key(65364, None) is True
    assert ("on_key_press", 65364) in home.calls


def test_handle_key_routes_to_the_screen_that_is_visible():
    """The whole point: after switching, keys go to the NEW screen."""
    mgr = ScreenManager()
    home = StubScreen("home", key_result=True)
    systemd = StubScreen("systemd", key_result=True)
    mgr.register(home, is_home=True)
    mgr.register(systemd)
    mgr.build()
    mgr.switch_to("systemd")

    mgr.handle_key(65364, None)

    assert ("on_key_press", 65364) in systemd.calls
    assert ("on_key_press", 65364) not in home.calls


def test_handle_key_declines_when_screen_has_no_handler():
    mgr = ScreenManager()
    mgr.register(BareScreen("home"), is_home=True)
    mgr.build()

    assert mgr.handle_key(65364, None) is False


def test_handle_key_swallows_screen_exceptions():
    class Exploding(StubScreen):
        def on_key_press(self, keyval, state):
            raise RuntimeError("boom")

    mgr = ScreenManager()
    mgr.register(Exploding("home"), is_home=True)
    mgr.build()

    assert mgr.handle_key(65364, None) is False


# --- Accessors --------------------------------------------------------------

def test_get_returns_registered_screen():
    mgr = ScreenManager()
    home = StubScreen("home")
    mgr.register(home, is_home=True)

    assert mgr.get("home") is home
    assert mgr.get("missing") is None


def test_current_screen_is_none_before_build():
    mgr = ScreenManager()
    mgr.register(StubScreen("home"), is_home=True)

    assert mgr.current is None
    assert mgr.current_screen is None
    assert mgr.stack is None
