"""
Tests for the elephant-backed search handlers (symbols, files).

Both are prefix handlers, so the most valuable assertions are about
`matches()` — a handler that over-matches would shadow app search for
ordinary queries, which is the worst failure available to a launcher.
"""

import pytest

from search.handlers.files import FilesHandler
from search.handlers.symbols import SymbolsHandler
from services.elephant import ElephantItem


class FakeClient:
    """Stand-in for ElephantClient that records calls."""

    def __init__(self, items=None, available=True):
        self.items = items or []
        self.available = available
        self.queries = []
        self.activations = []

    def is_available(self):
        return self.available

    def query(self, providers, text="", limit=20):
        self.queries.append((providers, text, limit))
        return self.items

    def activate(self, provider, identifier, action):
        self.activations.append((provider, identifier, action))
        return True


def symbol_item(text="grinning face", char="😀"):
    return ElephantItem(
        identifier="sym1", text=text, provider="symbols",
        icon=char, actions=["run_cmd"],
    )


def file_item(path="/home/komi/repos/herdr/Cargo.toml"):
    return ElephantItem(
        identifier="f1", text=path, provider="files",
        preview_type="file", actions=["open", "opendir", "copyfile", "copypath"],
    )


# --- SymbolsHandler.matches -------------------------------------------------

@pytest.mark.parametrize("query,expected", [
    (":smile", True),
    (":a", True),
    ("  :smile  ", True),
    (":", False),          # bare prefix is not a query
    ("", False),
    ("smile", False),
    ("=1+1", False),
    ("!lock", False),
    ("f:thing", False),
])
def test_symbols_matches(query, expected):
    assert SymbolsHandler().matches(query) is expected


# --- FilesHandler.matches ---------------------------------------------------

@pytest.mark.parametrize("query,expected", [
    ("f:cargo", True),
    ("  f:cargo  ", True),
    ("f:", False),         # bare prefix is not a query
    ("", False),
    ("firefox", False),    # must NOT shadow an ordinary app search
    ("file manager", False),
    (":smile", False),
])
def test_files_matches(query, expected):
    assert FilesHandler().matches(query) is expected


def test_files_prefix_does_not_swallow_apps_beginning_with_f():
    """`firefox` starts with 'f' but not with 'f:' — a real regression risk."""
    handler = FilesHandler()

    assert handler.matches("firefox") is False
    assert handler.matches("f") is False


# --- Result mapping ---------------------------------------------------------

def test_symbol_result_puts_the_character_in_the_title():
    """A raw emoji is not a GTK icon name, so it must ride in the title."""
    handler = SymbolsHandler()
    handler.client = FakeClient([symbol_item()])

    result = handler.get_results(":grin")[0]

    assert "😀" in result.title
    assert "grinning face" in result.title
    assert result.icon == "face-smile"  # a real theme icon, not the char
    assert result.result_type == "symbol"


def test_file_result_splits_basename_and_directory():
    handler = FilesHandler()
    handler.client = FakeClient([file_item()])

    result = handler.get_results("f:cargo")[0]

    assert result.title == "Cargo.toml"
    assert result.description == "/home/komi/repos/herdr"


def test_handlers_strip_the_prefix_before_querying():
    handler = SymbolsHandler()
    handler.client = FakeClient([symbol_item()])

    handler.get_results(":smile")

    providers, text, _ = handler.client.queries[0]
    assert providers == "symbols"
    assert text == "smile"


def test_files_strips_its_two_character_prefix():
    handler = FilesHandler()
    handler.client = FakeClient([file_item()])

    handler.get_results("f:cargo.toml")

    assert handler.client.queries[0][1] == "cargo.toml"


# --- Empty and degraded states ----------------------------------------------

def test_no_matches_yields_one_explanatory_row():
    handler = SymbolsHandler()
    handler.client = FakeClient([])

    results = handler.get_results(":zzzz")

    assert len(results) == 1
    assert "No symbols" in results[0].title
    assert results[0].on_activate is None  # nothing to activate


def test_daemon_down_says_so_rather_than_looking_empty():
    handler = FilesHandler()
    handler.client = FakeClient([], available=False)

    results = handler.get_results("f:anything")

    assert "daemon unavailable" in results[0].description.lower()


def test_empty_term_after_prefix_returns_nothing():
    handler = SymbolsHandler()
    handler.client = FakeClient([symbol_item()])

    assert handler.get_results(":   ") == []


# --- Activation -------------------------------------------------------------

def test_activating_a_symbol_runs_the_run_cmd_action():
    handler = SymbolsHandler()
    handler.client = FakeClient([symbol_item()])
    result = handler.get_results(":grin")[0]

    result.on_activate()

    assert handler.client.activations == [("symbols", "sym1", "run_cmd")]


def test_activating_a_file_runs_the_open_action():
    handler = FilesHandler()
    handler.client = FakeClient([file_item()])
    result = handler.get_results("f:cargo")[0]

    result.on_activate()

    assert handler.client.activations == [("files", "f1", "open")]


# --- Registry metadata ------------------------------------------------------

def test_handlers_document_themselves_for_the_shortcuts_screen():
    for handler in (SymbolsHandler(), FilesHandler()):
        assert handler.prefixes
        assert handler.description
        assert handler.example.startswith(handler.prefixes[0])


def test_priorities_sit_below_app_search_fallback():
    """Both must be checked before app_search (1000), which always matches."""
    assert SymbolsHandler().priority < 1000
    assert FilesHandler().priority < 1000
