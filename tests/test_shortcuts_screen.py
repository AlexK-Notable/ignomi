"""
Tests for the shortcuts screen.

The whole point of this screen is that it is GENERATED from the live
router and screen registries. So the tests that matter are the ones
proving a newly registered handler or screen shows up without anyone
editing the shortcuts screen — i.e. that it cannot go stale.
"""

from screens.shortcuts import KEY_BINDINGS, ShortcutsScreen


class FakeHandler:
    def __init__(self, name, priority=100, prefixes=None, description="",
                 example="", prefix_help=None, trigger_label=""):
        self.name = name
        self.priority = priority
        if prefixes is not None:
            self.prefixes = prefixes
        if description:
            self.description = description
        if example:
            self.example = example
        if prefix_help is not None:
            self.prefix_help = prefix_help
        if trigger_label:
            self.trigger_label = trigger_label


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


# --- Per-prefix help (which engine is `gh:`?) -------------------------------

def test_each_prefix_gets_its_own_description_when_prefix_help_is_given():
    """The reported bug: five web rows all said "Search the web".

    Knowing that `gh:` exists is useless without knowing it is GitHub.
    """
    router = FakeRouter([
        FakeHandler(
            "web_search",
            prefixes=["?", "g:", "gh:"],
            description="Search the web",
            prefix_help={
                "?": "Search Kagi",
                "g:": "Search Google",
                "gh:": "Search GitHub",
            },
        ),
    ])

    prefixed, _ = ShortcutsScreen(router=router)._split_handlers()

    assert prefixed == [
        ("?…", "Search Kagi"),
        ("g:…", "Search Google"),
        ("gh:…", "Search GitHub"),
    ]


def test_prefix_missing_from_prefix_help_falls_back_to_description():
    router = FakeRouter([
        FakeHandler(
            "web_search",
            prefixes=["?", "x:"],
            description="Search the web",
            prefix_help={"?": "Search Kagi"},
        ),
    ])

    prefixed, _ = ShortcutsScreen(router=router)._split_handlers()

    assert prefixed[1] == ("x:…", "Search the web")


def test_real_web_search_handler_names_every_engine():
    """Against the real handler and its real default engine set."""
    from search.handlers.web_search import WebSearchHandler

    router = FakeRouter([WebSearchHandler()])

    prefixed, _ = ShortcutsScreen(router=router)._split_handlers()
    by_prefix = dict(prefixed)

    assert by_prefix["?…"] == "Search Kagi"
    assert by_prefix["g:…"] == "Search Google"
    assert by_prefix["w:…"] == "Search Wikipedia"
    assert by_prefix["gh:…"] == "Search GitHub"
    assert by_prefix["yt:…"] == "Search YouTube"


def test_web_engine_names_follow_user_configured_engines():
    """Engines are user-configurable, so the labels must track them."""
    from search.handlers.web_search import WebSearchHandler

    handler = WebSearchHandler(engines={
        "d:": {"name": "DuckDuckGo", "url": "https://duckduckgo.com/?q={query}"},
    })
    prefixed, _ = ShortcutsScreen(router=FakeRouter([handler]))._split_handlers()

    assert prefixed == [("d:…", "Search DuckDuckGo")]


# --- trigger_label (the "firefox" bug) --------------------------------------

def test_trigger_label_beats_example_for_unprefixed_handlers():
    """The reported bug: app search showed "firefox" as if it were a command.

    The fallback handler is triggered by *any* text, so that is what the
    key column has to say.
    """
    router = FakeRouter([
        FakeHandler(
            "app_search",
            description="Search installed applications (e.g. firefox)",
            example="firefox",
            trigger_label="any text",
        ),
    ])

    _, unprefixed = ShortcutsScreen(router=router)._split_handlers()

    assert unprefixed == [
        ("any text", "Search installed applications (e.g. firefox)")
    ]
    assert unprefixed[0][0] != "firefox"


def test_real_app_search_handler_says_any_text_not_firefox():
    """Against the real handler, since that is what the user saw."""
    from search.handlers.app_search import AppSearchHandler

    router = FakeRouter([AppSearchHandler()])

    _, unprefixed = ShortcutsScreen(router=router)._split_handlers()

    assert len(unprefixed) == 1
    left, right = unprefixed[0]
    assert left == "any text"
    assert "firefox" in right          # kept, but as an example
    assert not right.startswith("Default")


def test_real_controls_handler_names_its_other_keywords():
    """`volume` alone hid that brightness and mute also work."""
    from search.handlers.controls import SystemControlsHandler

    router = FakeRouter([SystemControlsHandler()])

    _, unprefixed = ShortcutsScreen(router=router)._split_handlers()

    _, right = unprefixed[0]
    assert "brightness" in right
    assert "mute" in right


def test_example_is_still_used_when_no_trigger_label_is_declared():
    router = FakeRouter([
        FakeHandler("controls", description="Sliders", example="volume"),
    ])

    _, unprefixed = ShortcutsScreen(router=router)._split_handlers()

    assert unprefixed == [("volume", "Sliders")]


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
