"""
Systemd Screen - Start / stop / restart a curated set of systemd units.

Reached from the home screen's nav bar; Escape returns there (policy
lives in RootPanel).

Why the unit list is curated
----------------------------
`SystemdService.units` looks cheap and is not: it calls `ListUnitFiles()`
and then `get_unit()` for every result, and each `get_unit()` is a
synchronous D-Bus `LoadUnit` round-trip *plus* a `DBusProxy`
construction. On a normal desktop that is 1000+ blocking calls on the
GTK main thread — the launcher would lock up for seconds on every open.

So the units shown here come from `data/systemd.toml`, and we resolve
them **lazily**, on first entry to the screen, not at construction. That
keeps launcher startup free of D-Bus work entirely.

Live state
----------
Each resolved unit is connected to `notify::is-active` once, at resolve
time. The callback refreshes whatever row currently represents that unit
(rows are rebuilt on filter, units are not), so state stays honest
without polling.
"""

import os
import sys
from pathlib import Path

import toml
from gi.repository import Gdk
from loguru import logger

from ignis import widgets

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "data" / "systemd.toml"

VALID_BUSES = ("session", "system")

# systemd's "you asked for a unit that doesn't exist" D-Bus error. Worth
# recognising by name: `get_unit()` does NOT raise for a bogus unit (the
# manager's LoadUnit happily returns a stub whose is_active is False), so
# a typo'd unit name in systemd.toml looks exactly like a stopped service
# until you press a button. Catching this on the first action is how the
# row learns it is really unavailable.
NO_SUCH_UNIT = "NoSuchUnit"


def humanize_dbus_error(exc) -> str:
    """Reduce a GDBus error to the part a human wants to read.

    Raw form::

        g-io-error-quark: GDBus.Error:org.freedesktop.systemd1.NoSuchUnit:
        Unit foo.service not found. (36)

    Wanted::

        Unit foo.service not found.

    Anything that doesn't match the GDBus shape is returned unchanged, so
    non-D-Bus exceptions still say something useful.
    """
    text = str(exc).strip()

    marker = "GDBus.Error:"
    if marker in text:
        # Drop everything up to and including the error-name segment.
        tail = text.split(marker, 1)[1]
        if ": " in tail:
            text = tail.split(": ", 1)[1].strip()

    # Trailing GLib error code, e.g. " (36)".
    if text.endswith(")") and "(" in text:
        head, _, code = text.rpartition("(")
        if code[:-1].strip().isdigit():
            text = head.strip()

    return text


def load_unit_configs(path=None) -> list[dict]:
    """Read unit definitions from a systemd.toml file.

    Pure and side-effect free apart from reading the file — kept at
    module level so it can be tested without GTK or D-Bus.

    Malformed entries are skipped with a warning rather than raising:
    one bad line in a config file must not cost the user their launcher.

    Args:
        path: config file path. Defaults to `data/systemd.toml`.

    Returns:
        List of dicts with keys: unit, description, bus, icon.
        Empty list if the file is missing or unreadable.
    """
    config_path = Path(path) if path is not None else DEFAULT_CONFIG_PATH

    if not config_path.exists():
        logger.info(f"[systemd] no config at {config_path}; screen will be empty")
        return []

    try:
        data = toml.load(config_path)
    except Exception:
        logger.exception(f"[systemd] could not parse {config_path}")
        return []

    entries = data.get("units", [])
    if not isinstance(entries, list):
        logger.warning(f"[systemd] 'units' in {config_path} is not a list of tables")
        return []

    configs = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            logger.warning(f"[systemd] entry #{index} is not a table; skipping")
            continue

        unit = entry.get("unit")
        if not unit or not isinstance(unit, str):
            logger.warning(f"[systemd] entry #{index} has no 'unit' field; skipping")
            continue

        bus = entry.get("bus", "session")
        if bus not in VALID_BUSES:
            logger.warning(
                f"[systemd] '{unit}' has invalid bus '{bus}'; using 'session'"
            )
            bus = "session"

        configs.append({
            "unit": unit,
            "description": entry.get("description", ""),
            "bus": bus,
            "icon": entry.get("icon", "system-run"),
        })

    return configs


class SystemdScreen:
    """Screen listing curated systemd units with start/stop/restart."""

    name = "systemd"
    title = "Systemd"
    icon = "system-run"
    show_in_nav = True
    description = "Start, stop and restart your systemd units"

    def __init__(self, config_path=None):
        self.unit_configs = load_unit_configs(config_path)

        # bus type -> SystemdService (created on demand)
        self._services: dict = {}
        # unit name -> SystemdUnit, or None when resolution failed
        self._units: dict = {}
        # unit name -> the status dot Label of its current row
        self._dots: dict = {}

        self._resolved = False

        self._filter_entry = None
        self._list_box = None
        self._status_label = None

    # --- Screen protocol ----------------------------------------------------

    def create_widget(self):
        """Build the systemd screen content.

        No D-Bus work happens here — only widget construction. Units are
        resolved on first `on_enter()`.
        """
        back_button = widgets.Button(
            css_classes=["systemd-back"],
            on_click=lambda _: self._go_home(),
            child=widgets.Box(
                spacing=6,
                child=[
                    widgets.Icon(image="go-previous", pixel_size=16),
                    widgets.Label(label="Back"),
                ],
            ),
        )

        header = widgets.Box(
            spacing=12,
            css_classes=["systemd-header"],
            child=[
                back_button,
                widgets.Label(
                    label="Systemd Units",
                    css_classes=["systemd-title"],
                    hexpand=True,
                    xalign=0,
                ),
            ],
        )

        self._filter_entry = widgets.Entry(
            placeholder_text="Filter units...",
            css_classes=["search-entry", "systemd-filter"],
            on_change=lambda _: self._rebuild_rows(),
        )

        self._list_box = widgets.ListBox(css_classes=["search-results"])

        self._status_label = widgets.Label(
            label="",
            css_classes=["systemd-status"],
            halign="center",
        )

        panel = widgets.Box(
            vertical=True,
            spacing=8,
            css_classes=["panel", "systemd-panel"],
            child=[
                header,
                self._filter_entry,
                widgets.Scroll(
                    hexpand=True,
                    max_content_height=500,
                    propagate_natural_height=True,
                    child=self._list_box,
                ),
                self._status_label,
            ],
        )

        return widgets.Box(
            vertical=True,
            hexpand=True,
            vexpand=True,
            halign="center",
            valign="center",
            child=[panel],
        )

    def on_enter(self):
        """Resolve units (once) and draw the list."""
        if not self._resolved:
            self._resolve_units()
            self._resolved = True
        self._rebuild_rows()
        if self._filter_entry is not None:
            self._filter_entry.grab_focus()

    def on_leave(self):
        """Clear the filter so the screen is fresh next time."""
        if self._filter_entry is not None:
            self._filter_entry.set_text("")

    def on_key_press(self, keyval, state) -> bool:
        """Up/Down move the selection, Enter toggles the selected unit."""
        if self._list_box is None:
            return False

        rows = self._list_box.rows
        if not rows:
            return False

        selected = self._list_box.get_selected_row()
        current_idx = selected.get_index() if selected else -1

        if keyval == Gdk.KEY_Down:
            if current_idx < len(rows) - 1:
                self._list_box.select_row(rows[current_idx + 1])
            return True

        if keyval == Gdk.KEY_Up:
            if current_idx > 0:
                self._list_box.select_row(rows[current_idx - 1])
            return True

        if keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            if selected is not None:
                unit_name = getattr(selected, "_ignomi_unit", None)
                if unit_name:
                    self._toggle(unit_name)
            return True

        return False

    # --- Unit resolution ----------------------------------------------------

    def _get_service(self, bus: str):
        """Return (and cache) the SystemdService for a bus type."""
        if bus in self._services:
            return self._services[bus]

        try:
            from ignis.services.systemd import SystemdService

            service = SystemdService.get_default(bus)
        except Exception:
            logger.exception(f"[systemd] could not reach the {bus} bus")
            service = None

        self._services[bus] = service
        return service

    def _resolve_units(self):
        """Look up every configured unit over D-Bus, once.

        A unit that cannot be resolved (not installed, bus unreachable)
        is recorded as None and rendered as an 'unavailable' row rather
        than being silently dropped — a missing unit you configured is
        information, not noise.
        """
        for config in self.unit_configs:
            unit_name = config["unit"]
            service = self._get_service(config["bus"])

            if service is None:
                self._units[unit_name] = None
                continue

            try:
                unit = service.get_unit(unit_name)
            except Exception:
                logger.warning(f"[systemd] could not resolve '{unit_name}'")
                self._units[unit_name] = None
                continue

            self._units[unit_name] = unit

            # Connect once, here — rows come and go with filtering, units
            # do not, so this is the stable place to listen.
            try:
                unit.connect(
                    "notify::is-active",
                    lambda _u, _p, name=unit_name: self._refresh_dot(name),
                )
            except Exception:
                logger.warning(f"[systemd] no live state for '{unit_name}'")

        logger.debug(f"[systemd] resolved {len(self._units)} units")

    # --- Rendering ----------------------------------------------------------

    def _visible_configs(self) -> list[dict]:
        """Configs matching the current filter text."""
        query = ""
        if self._filter_entry is not None:
            query = (self._filter_entry.text or "").strip().lower()

        if not query:
            return self.unit_configs

        return [
            c for c in self.unit_configs
            if query in c["unit"].lower() or query in c["description"].lower()
        ]

    def _rebuild_rows(self):
        """Redraw the unit list from scratch for the current filter."""
        if self._list_box is None:
            return

        self._list_box.remove_all()
        self._dots.clear()

        configs = self._visible_configs()

        for config in configs:
            self._list_box.append(self._create_row(config))

        rows = self._list_box.rows
        if rows:
            self._list_box.select_row(rows[0])

        if self._status_label is not None:
            if not self.unit_configs:
                self._status_label.set_label(
                    "No units configured — see launcher/data/systemd.toml"
                )
            elif not configs:
                self._status_label.set_label("No units match that filter")
            else:
                self._status_label.set_label("Enter toggles · Esc goes back")

    def _create_row(self, config: dict):
        """Build one unit row: status dot, name/description, actions."""
        unit_name = config["unit"]
        unit = self._units.get(unit_name)
        available = unit is not None

        dot = widgets.Label(
            label="●",
            css_classes=["systemd-dot"] + self._dot_classes(unit_name),
        )
        self._dots[unit_name] = dot

        text_block = widgets.Box(
            vertical=True,
            spacing=2,
            hexpand=True,
            child=[
                widgets.Label(
                    label=unit_name,
                    css_classes=["app-name"],
                    xalign=0,
                    halign="start",
                    ellipsize="end",
                    max_width_chars=34,
                ),
                widgets.Label(
                    label=(
                        config["description"] if available
                        else "unavailable — not installed or bus unreachable"
                    ),
                    css_classes=["app-description"],
                    xalign=0,
                    halign="start",
                    ellipsize="end",
                    max_width_chars=44,
                ),
            ],
        )

        actions = widgets.Box(
            spacing=4,
            halign="end",
            valign="center",
            child=[
                self._action_button("Start", unit_name, "start", available),
                self._action_button("Stop", unit_name, "stop", available),
                self._action_button("Restart", unit_name, "restart", available),
            ],
        )

        row = widgets.ListBoxRow(
            css_classes=["app-item", "result-item", "systemd-row"],
            child=widgets.Box(
                spacing=10,
                child=[
                    widgets.Icon(image=config["icon"], pixel_size=20),
                    dot,
                    text_block,
                    actions,
                ],
            ),
        )
        # Stash the unit name so keyboard activation can find it.
        row._ignomi_unit = unit_name
        return row

    def _action_button(self, label: str, unit_name: str, action: str, enabled: bool):
        """One start/stop/restart button."""
        button = widgets.Button(
            css_classes=["systemd-action", f"systemd-action-{action}"],
            on_click=lambda _, n=unit_name, a=action: self._do_action(n, a),
            child=widgets.Label(label=label),
        )
        if not enabled:
            button.set_sensitive(False)
        return button

    def _dot_classes(self, unit_name: str) -> list[str]:
        """CSS state classes for a unit's status dot."""
        unit = self._units.get(unit_name)
        if unit is None:
            return ["systemd-dot-unknown"]
        try:
            return ["systemd-dot-active" if unit.is_active else "systemd-dot-inactive"]
        except Exception:
            return ["systemd-dot-unknown"]

    def _refresh_dot(self, unit_name: str):
        """Repaint one unit's status dot (called from notify::is-active)."""
        dot = self._dots.get(unit_name)
        if dot is None:
            return  # currently filtered out — nothing to repaint
        dot.set_css_classes(["systemd-dot"] + self._dot_classes(unit_name))

    # --- Actions ------------------------------------------------------------

    def _do_action(self, unit_name: str, action: str):
        """Run start/stop/restart on a unit.

        systemd returns as soon as the job is *enqueued*, so these calls
        are fast enough to make synchronously. Failures (missing polkit
        agent on the system bus, unit not found) are logged and surfaced
        in the status line rather than raised — a failed unit action must
        never take the launcher down with it.
        """
        unit = self._units.get(unit_name)
        if unit is None:
            self._set_status(f"{unit_name} is unavailable")
            return

        method = getattr(unit, action, None)
        if method is None:
            self._set_status(f"Unknown action '{action}'")
            return

        try:
            method()
            logger.info(f"[systemd] {action} {unit_name}")
            self._set_status(f"{action.capitalize()}ed {unit_name}")
        except Exception as exc:
            logger.exception(f"[systemd] {action} failed for {unit_name}")
            self._set_status(f"{action} failed — {humanize_dbus_error(exc)}")

            # A unit that doesn't exist resolved cleanly earlier (see
            # NO_SUCH_UNIT), so this failure is the first honest signal
            # that the name in systemd.toml is wrong. Record it, and the
            # row repaints as unavailable instead of pretending to be a
            # stopped service.
            if NO_SUCH_UNIT in str(exc):
                self._units[unit_name] = None

        self._refresh_dot(unit_name)

    def _toggle(self, unit_name: str):
        """Enter-key behaviour: stop an active unit, start an inactive one."""
        unit = self._units.get(unit_name)
        if unit is None:
            self._set_status(f"{unit_name} is unavailable")
            return
        try:
            active = unit.is_active
        except Exception:
            active = False
        self._do_action(unit_name, "stop" if active else "start")

    def _set_status(self, message: str):
        if self._status_label is not None:
            self._status_label.set_label(message)

    def _go_home(self):
        """Back button — return to the home screen."""
        from panels.root import RootPanel

        root = RootPanel.get_default()
        if root is not None:
            root.screens.go_home()
