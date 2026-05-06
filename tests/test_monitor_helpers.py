"""
Tests for monitor-detection helpers in utils/helpers.py.

These functions wrap HyprlandService IPC + Gdk monitor enumeration. Both
have been bug sites in past sprints. Tests use canned IPC responses
rather than touching a real compositor.
"""

from unittest.mock import MagicMock, patch

import pytest

import utils.helpers as helpers
from utils.helpers import (
    _hyprland_name_to_ignis_index,
    get_monitor_under_cursor,
    hyprland_monitor_to_ignis_monitor,
)


def _make_gdk_monitor(connector: str):
    """Build a fake Gdk monitor object that returns a connector name."""
    m = MagicMock()
    m.get_connector.return_value = connector
    return m


def _make_gdk_display(monitors_list):
    """Build a fake Gdk.Display whose get_monitors() returns these monitors."""
    display = MagicMock()
    monitors_iface = MagicMock()
    monitors_iface.get_n_items.return_value = len(monitors_list)
    monitors_iface.get_item.side_effect = lambda i: monitors_list[i]
    display.get_monitors.return_value = monitors_iface
    return display


def _make_hypr_monitor(mid: int, name: str, x: int, y: int, w: int, h: int):
    """Build a fake Hyprland monitor record."""
    m = MagicMock()
    m.id = mid
    m.name = name
    m.x = x
    m.y = y
    m.width = w
    m.height = h
    return m


class TestHyprlandNameToIgnisIndex:
    """Connector-name → GTK index lookup."""

    def test_finds_first_monitor(self):
        display = _make_gdk_display([
            _make_gdk_monitor("DP-1"),
            _make_gdk_monitor("HDMI-A-1"),
        ])
        with patch.object(helpers.Gdk.Display, "get_default", return_value=display):
            assert _hyprland_name_to_ignis_index("DP-1") == 0

    def test_finds_second_monitor(self):
        display = _make_gdk_display([
            _make_gdk_monitor("DP-1"),
            _make_gdk_monitor("HDMI-A-1"),
        ])
        with patch.object(helpers.Gdk.Display, "get_default", return_value=display):
            assert _hyprland_name_to_ignis_index("HDMI-A-1") == 1

    def test_unknown_connector_returns_zero(self):
        display = _make_gdk_display([_make_gdk_monitor("DP-1")])
        with patch.object(helpers.Gdk.Display, "get_default", return_value=display):
            assert _hyprland_name_to_ignis_index("DP-99") == 0

    def test_no_display_returns_zero(self):
        with patch.object(helpers.Gdk.Display, "get_default", return_value=None):
            assert _hyprland_name_to_ignis_index("DP-1") == 0


class TestHyprlandMonitorToIgnisMonitor:
    """Hyprland numeric ID → GTK index, via HyprlandService."""

    def test_resolves_via_hyprland_service(self):
        gdk_display = _make_gdk_display([_make_gdk_monitor("DP-1")])
        hypr = MagicMock()
        hypr.monitors = [_make_hypr_monitor(0, "DP-1", 0, 0, 3840, 2160)]
        with patch.object(helpers.HyprlandService, "get_default", return_value=hypr), \
             patch.object(helpers.Gdk.Display, "get_default", return_value=gdk_display):
            assert hyprland_monitor_to_ignis_monitor(0) == 0

    def test_unknown_hyprland_id_returns_zero(self):
        hypr = MagicMock()
        hypr.monitors = [_make_hypr_monitor(0, "DP-1", 0, 0, 3840, 2160)]
        with patch.object(helpers.HyprlandService, "get_default", return_value=hypr):
            assert hyprland_monitor_to_ignis_monitor(99) == 0

    def test_swallows_exceptions(self):
        with patch.object(helpers.HyprlandService, "get_default",
                          side_effect=RuntimeError("ipc dead")):
            assert hyprland_monitor_to_ignis_monitor(0) == 0


class TestGetMonitorUnderCursor:
    """Cursor position → containing monitor → GTK index."""

    def _setup(self, cursor_xy: str, monitors_geom: list):
        """Wire up HyprlandService.send_command + .monitors + Gdk display."""
        hypr = MagicMock()
        hypr.send_command.return_value = cursor_xy
        hypr.monitors = monitors_geom
        gdk_display = _make_gdk_display([
            _make_gdk_monitor(m.name) for m in monitors_geom
        ])
        return hypr, gdk_display

    def test_cursor_in_first_monitor(self):
        hypr, gdk = self._setup(
            cursor_xy="100, 100",
            monitors_geom=[
                _make_hypr_monitor(0, "DP-1", 0, 0, 1920, 1080),
                _make_hypr_monitor(1, "DP-2", 1920, 0, 1920, 1080),
            ],
        )
        with patch.object(helpers.HyprlandService, "get_default", return_value=hypr), \
             patch.object(helpers.Gdk.Display, "get_default", return_value=gdk):
            assert get_monitor_under_cursor() == 0

    def test_cursor_in_second_monitor(self):
        hypr, gdk = self._setup(
            cursor_xy="2500, 500",
            monitors_geom=[
                _make_hypr_monitor(0, "DP-1", 0, 0, 1920, 1080),
                _make_hypr_monitor(1, "DP-2", 1920, 0, 1920, 1080),
            ],
        )
        with patch.object(helpers.HyprlandService, "get_default", return_value=hypr), \
             patch.object(helpers.Gdk.Display, "get_default", return_value=gdk):
            assert get_monitor_under_cursor() == 1

    def test_malformed_cursorpos_response_returns_zero(self):
        hypr, gdk = self._setup(
            cursor_xy="garbage",
            monitors_geom=[_make_hypr_monitor(0, "DP-1", 0, 0, 1920, 1080)],
        )
        with patch.object(helpers.HyprlandService, "get_default", return_value=hypr), \
             patch.object(helpers.Gdk.Display, "get_default", return_value=gdk):
            assert get_monitor_under_cursor() == 0

    def test_swallows_ipc_exceptions(self):
        with patch.object(helpers.HyprlandService, "get_default",
                          side_effect=RuntimeError("hypr down")):
            assert get_monitor_under_cursor() == 0
