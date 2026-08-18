"""
Tests for the systemd screen.

Two halves:

  * `load_unit_configs` — pure file parsing, exercised against real TOML
    files written to tmp_path (no mocked filesystem, per suite policy).
  * `SystemdScreen` action handling — exercised with fake unit objects
    injected into the resolved-units map. Real D-Bus is out of scope for
    a unit test, but "does clicking Stop call stop()", "does a failing
    unit take the launcher down", and "does Enter toggle the right way"
    are exactly the bugs worth catching.
"""

from types import SimpleNamespace

import pytest
import toml

from screens.systemd import (
    SystemdScreen,
    humanize_dbus_error,
    load_unit_configs,
)


class FakeUnit:
    """Stand-in for ignis SystemdUnit."""

    def __init__(self, is_active=False, fail=False):
        self.is_active = is_active
        self.fail = fail
        self.calls = []

    def _record(self, action):
        self.calls.append(action)
        if self.fail:
            raise RuntimeError("dbus exploded")

    def start(self):
        self._record("start")

    def stop(self):
        self._record("stop")

    def restart(self):
        self._record("restart")


def _write(path, data):
    path.write_text(toml.dumps(data))
    return path


# --- load_unit_configs ------------------------------------------------------

def test_loads_units_from_real_file(tmp_systemd_config):
    configs = load_unit_configs(tmp_systemd_config)

    assert [c["unit"] for c in configs] == ["waybar.service", "sshd.service"]


def test_applies_defaults_for_optional_fields(tmp_path):
    path = _write(tmp_path / "s.toml", {"units": [{"unit": "a.service"}]})

    config = load_unit_configs(path)[0]

    assert config["description"] == ""
    assert config["bus"] == "session"
    assert config["icon"] == "system-run"


def test_explicit_bus_is_preserved(tmp_systemd_config):
    configs = load_unit_configs(tmp_systemd_config)
    by_name = {c["unit"]: c for c in configs}

    assert by_name["waybar.service"]["bus"] == "session"
    assert by_name["sshd.service"]["bus"] == "system"


def test_invalid_bus_falls_back_to_session(tmp_path):
    path = _write(
        tmp_path / "s.toml",
        {"units": [{"unit": "a.service", "bus": "banana"}]},
    )

    assert load_unit_configs(path)[0]["bus"] == "session"


def test_order_is_preserved(tmp_path):
    """On-screen order is config order — array-of-tables keeps it."""
    path = _write(
        tmp_path / "s.toml",
        {"units": [{"unit": f"{n}.service"} for n in ("z", "a", "m")]},
    )

    assert [c["unit"] for c in load_unit_configs(path)] == [
        "z.service", "a.service", "m.service",
    ]


def test_missing_file_yields_empty_list(tmp_path):
    assert load_unit_configs(tmp_path / "nope.toml") == []


def test_malformed_toml_yields_empty_list_instead_of_raising(tmp_path):
    path = tmp_path / "s.toml"
    path.write_text("this is [not valid toml === ")

    assert load_unit_configs(path) == []


def test_units_key_of_wrong_type_yields_empty_list(tmp_path):
    path = _write(tmp_path / "s.toml", {"units": {"unit": "a.service"}})

    assert load_unit_configs(path) == []


def test_entry_without_unit_field_is_skipped_not_fatal(tmp_path):
    """One bad entry must not cost the user the whole screen."""
    path = _write(
        tmp_path / "s.toml",
        {"units": [{"description": "orphan"}, {"unit": "good.service"}]},
    )

    configs = load_unit_configs(path)

    assert [c["unit"] for c in configs] == ["good.service"]


def test_missing_units_key_yields_empty_list(tmp_path):
    path = _write(tmp_path / "s.toml", {"something_else": 1})

    assert load_unit_configs(path) == []


# --- Screen construction ----------------------------------------------------

def test_screen_exposes_the_screen_protocol_surface():
    screen = SystemdScreen(config_path=None)

    assert screen.name == "systemd"
    assert screen.title
    assert screen.icon
    assert screen.show_in_nav is True
    assert callable(screen.create_widget)


def test_construction_does_no_dbus_work(tmp_systemd_config):
    """Units resolve on first on_enter(), never at construction.

    This is the guard on the performance decision documented in
    screens/systemd.py — resolving at construction would put D-Bus
    round-trips on the launcher's startup path.
    """
    screen = SystemdScreen(config_path=tmp_systemd_config)

    assert screen._units == {}
    assert screen._services == {}
    assert screen._resolved is False


# --- Actions ----------------------------------------------------------------

@pytest.fixture
def screen(tmp_systemd_config):
    """A screen with units pre-resolved to fakes (skips D-Bus)."""
    s = SystemdScreen(config_path=tmp_systemd_config)
    s._units = {
        "waybar.service": FakeUnit(is_active=True),
        "sshd.service": FakeUnit(is_active=False),
    }
    s._resolved = True
    return s


@pytest.mark.parametrize("action", ["start", "stop", "restart"])
def test_action_calls_the_matching_unit_method(screen, action):
    screen._do_action("waybar.service", action)

    assert screen._units["waybar.service"].calls == [action]


def test_action_on_unresolved_unit_is_reported_not_raised(screen):
    screen._units["broken.service"] = None

    screen._do_action("broken.service", "start")  # must not raise


def test_action_on_unknown_unit_is_reported_not_raised(screen):
    screen._do_action("never-configured.service", "start")  # must not raise


def test_failing_unit_action_does_not_propagate(screen):
    """A D-Bus failure (e.g. no polkit agent) must not kill the launcher."""
    screen._units["waybar.service"] = FakeUnit(is_active=True, fail=True)

    screen._do_action("waybar.service", "start")  # must not raise

    assert screen._units["waybar.service"].calls == ["start"]


def test_unknown_action_name_is_reported_not_raised(screen):
    screen._do_action("waybar.service", "obliterate")

    assert screen._units["waybar.service"].calls == []


def test_toggle_stops_an_active_unit(screen):
    screen._toggle("waybar.service")

    assert screen._units["waybar.service"].calls == ["stop"]


def test_toggle_starts_an_inactive_unit(screen):
    screen._toggle("sshd.service")

    assert screen._units["sshd.service"].calls == ["start"]


def test_toggle_on_unresolved_unit_is_safe(screen):
    screen._units["broken.service"] = None

    screen._toggle("broken.service")  # must not raise


# --- Status dot -------------------------------------------------------------

def test_dot_reflects_active_state(screen):
    assert "systemd-dot-active" in screen._dot_classes("waybar.service")
    assert "systemd-dot-inactive" in screen._dot_classes("sshd.service")


def test_dot_for_unresolved_unit_is_unknown(screen):
    screen._units["broken.service"] = None

    assert "systemd-dot-unknown" in screen._dot_classes("broken.service")


def test_dot_for_unit_that_raises_on_read_is_unknown(screen):
    class Hostile:
        @property
        def is_active(self):
            raise RuntimeError("bus went away")

    screen._units["hostile.service"] = Hostile()

    assert "systemd-dot-unknown" in screen._dot_classes("hostile.service")


def test_refresh_dot_for_filtered_out_unit_is_a_noop(screen):
    """Rows come and go with filtering; a signal for a hidden row is fine."""
    screen._dots = {}

    screen._refresh_dot("waybar.service")  # must not raise


# --- Filtering --------------------------------------------------------------

def test_no_filter_shows_every_unit(screen):
    assert len(screen._visible_configs()) == 2


def test_filter_matches_unit_name(screen):
    screen._filter_entry = SimpleNamespace(text="way")

    assert [c["unit"] for c in screen._visible_configs()] == ["waybar.service"]


def test_filter_matches_description(screen):
    screen._filter_entry = SimpleNamespace(text="ssh daemon")

    assert [c["unit"] for c in screen._visible_configs()] == ["sshd.service"]


def test_filter_is_case_insensitive(screen):
    screen._filter_entry = SimpleNamespace(text="WAYBAR")

    assert [c["unit"] for c in screen._visible_configs()] == ["waybar.service"]


def test_filter_with_no_matches_returns_empty(screen):
    screen._filter_entry = SimpleNamespace(text="zzzzz")

    assert screen._visible_configs() == []


def test_blank_filter_text_shows_everything(screen):
    screen._filter_entry = SimpleNamespace(text="   ")

    assert len(screen._visible_configs()) == 2


# --- Error humanising -------------------------------------------------------
#
# The raw string below is a VERBATIM capture from this machine's session
# bus (ignis SystemdUnit.start on a unit that does not exist), not an
# invented shape — the parsing has to survive the real format.

REAL_DBUS_ERROR = (
    "g-io-error-quark: GDBus.Error:org.freedesktop.systemd1.NoSuchUnit: "
    "Unit definitely-not-real-ignomi-probe.service not found. (36)"
)


def test_humanize_strips_gdbus_scaffolding_from_a_real_error():
    assert humanize_dbus_error(Exception(REAL_DBUS_ERROR)) == (
        "Unit definitely-not-real-ignomi-probe.service not found."
    )


def test_humanize_leaves_a_plain_message_alone():
    assert humanize_dbus_error(Exception("something broke")) == "something broke"


def test_humanize_does_not_eat_legitimate_trailing_parens():
    """Only a trailing numeric GLib code is stripped, not real text."""
    assert humanize_dbus_error(Exception("failed (permission denied)")) == (
        "failed (permission denied)"
    )


def test_humanize_handles_empty_exception():
    assert humanize_dbus_error(Exception("")) == ""


# --- Learning that a configured unit does not exist -------------------------

def test_nosuchunit_failure_marks_the_unit_unavailable(screen):
    """A typo in systemd.toml resolves fine, so the action is the tell.

    `get_unit()` returns a working stub for a bogus unit name (verified
    against the real bus), so the row would otherwise sit there looking
    like a merely-stopped service forever.
    """
    class Phantom:
        is_active = False

        def start(self):
            raise RuntimeError(REAL_DBUS_ERROR)

    screen._units["ghost.service"] = Phantom()

    screen._do_action("ghost.service", "start")

    assert screen._units["ghost.service"] is None
    assert "systemd-dot-unknown" in screen._dot_classes("ghost.service")


def test_ordinary_failure_does_not_mark_the_unit_unavailable(screen):
    """A permission error means the unit exists — don't disable its row."""
    screen._units["waybar.service"] = FakeUnit(is_active=True, fail=True)

    screen._do_action("waybar.service", "start")

    assert screen._units["waybar.service"] is not None
