"""
Tests for launcher lifecycle helpers in utils/helpers.py.

Currently focuses on launch_app — the most-trafficked code path. These
tests validate the N17 fix: a failed app.launch() must not (a) leave the
launcher visible forever, (b) record a frecency entry for a broken app,
or (c) propagate the exception to the caller.

Tests for toggle_launcher / close_launcher / _close_* are intentionally
absent here pending the A1 single-window refactor — those internals are
about to change shape.
"""

from unittest.mock import MagicMock, patch

import pytest

from utils.helpers import launch_app


class TestLaunchAppHappyPath:
    """Successful launches record frecency and schedule auto-close."""

    def test_records_frecency_on_success(self):
        app = MagicMock()
        app.id = "firefox.desktop"
        frecency = MagicMock()
        with patch("utils.helpers.GLib") as mock_glib:
            launch_app(app, frecency, close_delay_ms=300)
        app.launch.assert_called_once()
        frecency.record_launch.assert_called_once_with("firefox.desktop")
        mock_glib.timeout_add.assert_called_once()

    def test_close_timer_uses_provided_delay(self):
        app = MagicMock()
        frecency = MagicMock()
        with patch("utils.helpers.GLib") as mock_glib:
            launch_app(app, frecency, close_delay_ms=500)
        # First arg to GLib.timeout_add is the delay
        delay_arg = mock_glib.timeout_add.call_args[0][0]
        assert delay_arg == 500


class TestLaunchAppFailureModes:
    """N17 — launch failures must close launcher and skip frecency."""

    def test_close_timer_still_fires_when_launch_raises(self):
        """Broken .desktop must not strand the launcher visible."""
        app = MagicMock()
        app.id = "broken.desktop"
        app.launch.side_effect = RuntimeError("missing binary")
        frecency = MagicMock()
        with patch("utils.helpers.GLib") as mock_glib:
            launch_app(app, frecency, close_delay_ms=300)
        mock_glib.timeout_add.assert_called_once()

    def test_frecency_skipped_when_launch_raises(self):
        """Broken apps must not climb the frequent list."""
        app = MagicMock()
        app.id = "broken.desktop"
        app.launch.side_effect = RuntimeError("missing binary")
        frecency = MagicMock()
        with patch("utils.helpers.GLib"):
            launch_app(app, frecency, close_delay_ms=300)
        frecency.record_launch.assert_not_called()

    def test_exception_does_not_propagate(self):
        """Caller (panel button handler) should not see the launch error."""
        app = MagicMock()
        app.id = "broken.desktop"
        app.launch.side_effect = RuntimeError("missing binary")
        frecency = MagicMock()
        with patch("utils.helpers.GLib"):
            # Should not raise
            launch_app(app, frecency, close_delay_ms=300)

    def test_close_timer_still_fires_when_frecency_raises(self):
        """If frecency.record_launch raises, the launcher still closes."""
        app = MagicMock()
        app.id = "good.desktop"
        frecency = MagicMock()
        frecency.record_launch.side_effect = RuntimeError("db locked")
        with patch("utils.helpers.GLib") as mock_glib:
            launch_app(app, frecency, close_delay_ms=300)
        app.launch.assert_called_once()
        mock_glib.timeout_add.assert_called_once()
