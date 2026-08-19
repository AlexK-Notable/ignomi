"""
Tests for the elephant client.

The NDJSON fixtures below are VERBATIM captures from this machine's
elephant 2.22.0 daemon, not invented shapes — the parser has to survive
the real output, including the fields that differ per provider
(clipboard rows carry `subtext`/`preview` and no `query`; symbol rows
carry the character in `icon`; file rows carry a path in `text`).

The activate arity test is the important one: elephant's CLI *panics*
with an index error on fewer than five semicolon-separated fields rather
than printing usage, so an off-by-one there is a crash, not a message.
"""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from services.elephant import ElephantClient, ElephantItem


SYMBOL_LINE = (
    '{"query":"smile","item":{"identifier":"34d4637c0412f2df0030332922d07885",'
    '"text":"beaming face with smiling eyes","icon":"\\ud83d\\ude01",'
    '"provider":"symbols","score":140,"actions":["run_cmd"]},"qid":1}'
)

CLIPBOARD_LINE = (
    '{"item":{"identifier":"06043961931cf680a195fc9ac3f56d54",'
    '"text":"git cherry-pick d17b9ca","subtext":"Tue, 18 Aug 2026 18:37:32 -0700",'
    '"provider":"clipboard","score":1000000,"preview":"git cherry-pick d17b9ca",'
    '"preview_type":"text","actions":["copy","edit","pin","remove"]},"qid":2}'
)

FILE_LINE = (
    '{"query":"toml","item":{"identifier":"2f3e324974bf31b3",'
    '"text":"/home/komi/repos/herdr/Cargo.toml","provider":"files","score":75,'
    '"preview":"/home/komi/repos/herdr/Cargo.toml","preview_type":"file",'
    '"actions":["open","opendir","copyfile","copypath"]},"qid":3}'
)


def _proc(stdout="", returncode=0, stderr=""):
    result = MagicMock()
    result.stdout = stdout
    result.stderr = stderr
    result.returncode = returncode
    return result


@pytest.fixture
def client():
    c = ElephantClient(timeout=1.0)
    return c


# --- ElephantItem parsing ---------------------------------------------------

def test_parses_a_real_symbol_row():
    items = ElephantClient._parse_ndjson(SYMBOL_LINE)

    assert len(items) == 1
    item = items[0]
    assert item.provider == "symbols"
    assert item.text == "beaming face with smiling eyes"
    assert item.icon == "😁"  # the character rides in `icon`, not `text`
    assert item.actions == ["run_cmd"]


def test_parses_a_real_clipboard_row():
    item = ElephantClient._parse_ndjson(CLIPBOARD_LINE)[0]

    assert item.provider == "clipboard"
    assert item.subtext.startswith("Tue, 18 Aug 2026")
    assert item.preview_type == "text"
    assert "remove" in item.actions


def test_parses_a_real_file_row():
    item = ElephantClient._parse_ndjson(FILE_LINE)[0]

    assert item.provider == "files"
    assert item.text == "/home/komi/repos/herdr/Cargo.toml"
    assert item.actions == ["open", "opendir", "copyfile", "copypath"]


def test_parses_multiple_ndjson_lines():
    """Output is newline-delimited JSON, NOT a JSON array."""
    stdout = "\n".join([SYMBOL_LINE, CLIPBOARD_LINE, FILE_LINE])

    assert len(ElephantClient._parse_ndjson(stdout)) == 3


def test_one_malformed_line_costs_one_row_not_the_batch():
    stdout = "\n".join([SYMBOL_LINE, "{not json at all", FILE_LINE])

    assert len(ElephantClient._parse_ndjson(stdout)) == 2


def test_blank_lines_are_ignored():
    stdout = f"\n\n{SYMBOL_LINE}\n\n"

    assert len(ElephantClient._parse_ndjson(stdout)) == 1


def test_empty_output_yields_no_items():
    assert ElephantClient._parse_ndjson("") == []


def test_payload_without_item_is_skipped():
    assert ElephantClient._parse_ndjson('{"qid":1}') == []


def test_item_without_identifier_is_skipped():
    """Identifier is what activate() needs; a row without one is useless."""
    line = '{"item":{"text":"orphan","provider":"files"},"qid":1}'

    assert ElephantClient._parse_ndjson(line) == []


def test_from_payload_defaults_missing_optional_fields():
    item = ElephantItem.from_payload({"item": {"identifier": "x", "text": "t"}})

    assert item.subtext == ""
    assert item.icon == ""
    assert item.score == 0
    assert item.actions == []


# --- Availability gating ----------------------------------------------------

def test_query_returns_empty_when_daemon_unavailable(client):
    with patch.object(client, "is_available", return_value=False):
        with patch("subprocess.run") as run:
            assert client.query("clipboard") == []
            run.assert_not_called()  # must not even spawn a process


def test_activate_refuses_when_daemon_unavailable(client):
    with patch.object(client, "is_available", return_value=False):
        with patch("subprocess.run") as run:
            assert client.activate("clipboard", "abc", "copy") is False
            run.assert_not_called()


# --- Query command construction ---------------------------------------------

def test_query_builds_semicolon_separated_content(client):
    """Elephant takes one positional `providers;query;limit` string."""
    with patch.object(client, "is_available", return_value=True):
        with patch("subprocess.run", return_value=_proc(SYMBOL_LINE)) as run:
            client.query("symbols", "smile", 20)

    argv = run.call_args[0][0]
    assert argv[:3] == ["elephant", "query", "--json"]
    assert argv[3] == "symbols;smile;20"


def test_query_supports_an_empty_search_term(client):
    """Clipboard uses an empty query to mean 'everything, by recency'."""
    with patch.object(client, "is_available", return_value=True):
        with patch("subprocess.run", return_value=_proc("")) as run:
            client.query("clipboard", "", 50)

    assert run.call_args[0][0][3] == "clipboard;;50"


# --- Query failure modes ----------------------------------------------------

def test_query_survives_a_timeout(client):
    with patch.object(client, "is_available", return_value=True):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("elephant", 1)):
            assert client.query("files", "x") == []


def test_query_survives_a_missing_binary(client):
    with patch.object(client, "is_available", return_value=True):
        with patch("subprocess.run", side_effect=FileNotFoundError()):
            assert client.query("files", "x") == []


def test_query_survives_a_nonzero_exit(client):
    with patch.object(client, "is_available", return_value=True):
        with patch("subprocess.run", return_value=_proc("", 1, "boom")):
            assert client.query("files", "x") == []


def test_query_survives_an_unexpected_exception(client):
    with patch.object(client, "is_available", return_value=True):
        with patch("subprocess.run", side_effect=RuntimeError("nope")):
            assert client.query("files", "x") == []


# --- Activate ---------------------------------------------------------------

def test_activate_sends_exactly_five_fields(client):
    """Fewer than five and the elephant CLI panics with an index error.

    This is the single most breakable contract in the integration: the
    CLI does not validate and print usage, it crashes.
    """
    with patch.object(client, "is_available", return_value=True):
        with patch("subprocess.run", return_value=_proc()) as run:
            client.activate("clipboard", "abc123", "copy")

    argv = run.call_args[0][0]
    assert argv[:2] == ["elephant", "activate"]
    content = argv[2]
    assert content == "clipboard;abc123;copy;;"
    assert content.count(";") == 4  # 5 fields


def test_activate_reports_success(client):
    with patch.object(client, "is_available", return_value=True):
        with patch("subprocess.run", return_value=_proc()):
            assert client.activate("files", "id", "open") is True


def test_activate_reports_failure_on_nonzero_exit(client):
    with patch.object(client, "is_available", return_value=True):
        with patch("subprocess.run", return_value=_proc("", 2, "nope")):
            assert client.activate("files", "id", "open") is False


def test_activate_survives_a_timeout(client):
    with patch.object(client, "is_available", return_value=True):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("elephant", 1)):
            assert client.activate("files", "id", "open") is False
