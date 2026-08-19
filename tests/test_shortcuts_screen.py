"""
Tests for the shortcuts screen.

The whole point of this screen is that it is GENERATED from the live
router and screen registries. So the tests that matter are the ones
proving a newly registered handler or screen shows up without anyone
editing the shortcuts screen — i.e. that it cannot go stale.
"""

from screens.shortcuts import KEY_BINDINGS, ShortcutsScreen


class FakeHandler:
    def __init__(self, name, priority=100, prefixes=None, description="", example=""):
        self.name = name
        self.priority = priority
        if prefixes is not None:
            self.prefixes = prefixes
        if description:
            self.description = description
        if example:
            self.example = example


class FakeRouter:
    def __init__(self, handlers):
        self._handlers = sorted(handlers, key=lambda h: h.priority)

    @property
    def handlers(self):
        return list(self._handlers)


class FakeScreen:
    def __init__(self, name, title=None, description=None, show_in_nav=True):
        self.name = name
        self.title = title or name.title()
        self.icon = "x"
        self.show_in_nav = show_in_nav
        if description is not None:
            self.description = description


class FakeManager:
    def __init__(self, screens):
        self._screens = screens

    def nav_screens(self):
        return [s for s in self._screens if getattr(s, "show_in_nav", True)]


# --- Handler documentation --------------------------------------------------

def test_prefixed_handler_appears_with_its_prefix():
    router = FakeRouter([
        FakeHandler("symbols", prefixes=[":"], description="Emoji", example=":smile"),
    ])

    prefixed, _ = ShortcutsScreen(router=router)._split_handlers()

    assert len(prefixed) == 1
    left, right = prefixed[0]
    assert left == ":…"
    assert "Emoji" in right
    assert ":smile" in right


def test_a_handler_with_several_prefixes_gets_a_row_each():
    """Web search declares five engines; none of them are guessable."""
    router = FakeRouter([
        FakeHandler(
            "web_search",
            prefixes=["?", "g:", "w:", "gh:", "yt:"],
            description="Search the web",
        ),
    ])

    prefixed, _ = ShortcutsScreen(router=router)._split_handlers()

    assert [left for left, _ in prefixed] == ["?…", "g:…", "w:…", "gh:…", "yt:…"]


def test_handler_without_prefixes_lands_in_the_unprefixed_group():
    router = FakeRouter([
        FakeHandler("controls", description="Volume sliders", example="volume"),
    ])

    prefixed, unprefixed = ShortcutsScreen(router=router)._split_handlers()

    assert prefixed == []
    assert unprefixed == [("volume", "Volume sliders")]


def test_handler_with_no_metadata_at_all_still_appears():
    """Documentation attributes are optional; a bare handler must not vanish."""
    router = FakeRouter([FakeHandler("mystery")])

    _, unprefixed = ShortcutsScreen(router=router)._split_handlers()

    assert unprefixed == [("mystery", "mystery")]


def test_example_not_matching_the_prefix_is_not_shown():
    """Guards against pairing a prefix row with an unrelated example."""
    router = FakeRouter([
        FakeHandler("odd", prefixes=["#"], description="Thing", example="unrelated"),
    ])

    _, right = ShortcutsScreen(router=router)._split_handlers()[0][0]

    assert "unrelated" not in right


def test_rows_follow_router_priority_order():
    router = FakeRouter([
        FakeHandler("late", priority=900, prefixes=["z:"]),
        FakeHandler("early", priority=10, prefixes=["a:"]),
    ])

    prefixed, _ = ShortcutsScreen(router=router)._split_handlers()

    assert [left for left, _ in prefixed] == ["a:…", "z:…"]


def test_a_newly_registered_handler_needs_no_edit_here():
    """The anti-staleness property, stated as a test.

    Adding a handler to the router is the ONLY step required for it to
    be documented.
    """
    router = FakeRouter([FakeHandler("existing", prefixes=["e:"])])
    before, _ = ShortcutsScreen(router=router)._split_handlers()

    router._handlers.append(FakeHandler("brand_new", priority=999, prefixes=["n:"]))
    after, _ = ShortcutsScreen(router=router)._split_handlers()

    assert len(after) == len(before) + 1
    assert "n:…" in [left for left, _ in after]


def test_no_router_degrades_to_empty_rather_than_raising():
    prefixed, unprefixed = ShortcutsScreen(router=None)._split_handlers()

    assert prefixed == []
    assert unprefixed == []


# --- Screen documentation ---------------------------------------------------

def test_screens_are_documented_from_the_registry():
    manager = FakeManager([
        FakeScreen("systemd", "Systemd", "Manage units"),
        FakeScreen("clipboard", "Clipboard", "Browse history"),
    ])

    rows = ShortcutsScreen(manager=manager)._screen_rows()

    assert rows == [("Systemd", "Manage units"), ("Clipboard", "Browse history")]


def test_the_shortcuts_screen_does_not_document_itself():
    manager = FakeManager([
        FakeScreen("shortcuts", "Shortcuts", "This screen"),
        FakeScreen("systemd", "Systemd", "Manage units"),
    ])

    rows = ShortcutsScreen(manager=manager)._screen_rows()

    assert [title for title, _ in rows] == ["Systemd"]


def test_screen_without_a_description_still_appears():
    manager = FakeManager([FakeScreen("bare", "Bare")])

    rows = ShortcutsScreen(manager=manager)._screen_rows()

    assert rows == [("Bare", "Open the panel")]


def test_screens_hidden_from_nav_are_not_documented():
    manager = FakeManager([FakeScreen("secret", show_in_nav=False)])

    assert ShortcutsScreen(manager=manager)._screen_rows() == []


def test_no_manager_degrades_to_empty():
    assert ShortcutsScreen(manager=None)._screen_rows() == []


# --- Screen protocol --------------------------------------------------------

def test_exposes_the_screen_protocol_surface():
    screen = ShortcutsScreen()

    assert screen.name == "shortcuts"
    assert screen.title
    assert screen.icon
    assert screen.show_in_nav is True
    assert callable(screen.create_widget)


def test_key_bindings_are_present_and_shaped():
    assert KEY_BINDINGS
    for entry in KEY_BINDINGS:
        key, description = entry
        assert key and description
