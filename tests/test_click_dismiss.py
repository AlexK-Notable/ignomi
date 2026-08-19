"""
Tests for click-outside-to-dismiss hit testing.

The launcher window covers the entire output, so "did the user click the
UI or the blurred desktop?" is not a geometry question — every point is
inside the window. `is_background_target` answers it by walking up from
the clicked widget looking for a content marker, which is pure logic and
tests directly with fake widgets.
"""

from panels.root import SOLID_CSS_CLASSES, is_background_target


class FakeWidget:
    """Minimal stand-in exposing the two methods the walk uses."""

    def __init__(self, classes=None, parent=None):
        self._classes = list(classes or [])
        self._parent = parent

    def get_css_classes(self):
        return self._classes

    def get_parent(self):
        return self._parent


def chain(*class_lists):
    """Build a parent chain, innermost (clicked) widget returned.

    chain(["panel"], ["home-screen"]) -> label whose parent is .panel,
    whose parent is .home-screen.
    """
    widget = None
    for classes in reversed(class_lists):
        widget = FakeWidget(classes, parent=widget)
    return widget


# --- Backdrop clicks (should dismiss) ---------------------------------------

def test_bare_widget_with_no_ancestors_is_background():
    assert is_background_target(FakeWidget()) is True


def test_layout_scaffolding_is_background():
    """The home screen's own Box is empty space between the panels."""
    picked = chain(["home-screen"], ["ignomi-window", "ignomi-launcher"])

    assert is_background_target(picked) is True


def test_backdrop_picture_chain_is_background():
    picked = chain([], [], ["ignomi-window"])

    assert is_background_target(picked) is True


# --- Content clicks (should NOT dismiss) ------------------------------------

def test_click_directly_on_a_panel_is_content():
    assert is_background_target(FakeWidget(["panel", "search-panel"])) is False


def test_click_deep_inside_a_panel_is_content():
    """A label inside a box inside the panel still counts as content."""
    picked = chain(
        ["app-name"],
        ["app-item"],
        ["panel", "bookmarks-panel"],
        ["home-screen"],
    )

    assert is_background_target(picked) is False


def test_click_on_a_nav_button_is_content():
    picked = chain(["nav-label"], ["nav-button"], ["nav-bar"], ["home-screen"])

    assert is_background_target(picked) is False


def test_click_inside_the_systemd_panel_is_content():
    picked = chain(["systemd-action"], ["systemd-row"], ["panel", "systemd-panel"])

    assert is_background_target(picked) is False


# --- The unresolvable-target case -------------------------------------------

def test_pick_returning_none_does_not_dismiss():
    """None means GTK could not resolve a target — do not guess "background".

    On a mapped full-screen window every click has a target, so None is
    an anomaly. The failure costs are asymmetric: treating it as content
    means an odd backdrop click doesn't close; treating it as background
    would make a malfunctioning pick() close the launcher on every click,
    including ones meant to launch an app.
    """
    assert is_background_target(None) is False


# --- Marker discipline ------------------------------------------------------

def test_panel_variant_class_alone_does_not_count_as_content():
    """Only the registered markers count, not the per-panel variants.

    Guards the convention: a screen that styles itself `.my-panel` but
    forgets the shared `.panel` class would silently fall through to the
    backdrop and dismiss on click.
    """
    assert is_background_target(FakeWidget(["search-panel"])) is True


def test_panel_is_a_registered_marker():
    """All four existing panels carry `panel`; that is why it's the key."""
    assert "panel" in SOLID_CSS_CLASSES
    assert "nav-bar" in SOLID_CSS_CLASSES


def test_custom_solid_classes_are_honoured():
    picked = FakeWidget(["something-custom"])

    assert is_background_target(picked, solid_classes={"something-custom"}) is False


# --- stop_at ----------------------------------------------------------------

def test_walk_stops_at_the_given_ancestor():
    """Nothing above the window should be consulted."""
    window = FakeWidget(["ignomi-window"])
    # A (contrived) solid ancestor ABOVE the window must not be reached.
    window._parent = FakeWidget(["panel"])
    picked = FakeWidget(["home-screen"], parent=window)

    assert is_background_target(picked, stop_at=window) is True


def test_stop_at_widget_itself_is_still_inspected():
    """The stop widget's own classes count before the walk halts."""
    window = FakeWidget(["panel"])
    picked = FakeWidget([], parent=window)

    assert is_background_target(picked, stop_at=window) is False


def test_walk_terminates_without_stop_at():
    """No stop_at given — the walk ends at the root, not in a loop."""
    picked = chain([], [], [], [])

    assert is_background_target(picked) is True
