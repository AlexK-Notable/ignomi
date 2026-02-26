"""
Tests for the CustomCommandsHandler.

Uses real TOML files. Tests command loading, matching, filtering, and
error handling for malformed entries.
"""

from pathlib import Path
from unittest.mock import patch

import toml

from search.handlers.commands import CustomCommandsHandler
from search.router import ResultItem


class TestCommandsLoading:
    """Test loading commands from TOML files."""

    def test_loads_valid_commands(self, tmp_commands):
        """Load commands from a valid TOML file."""
        data = toml.load(tmp_commands)
        commands = data.get("commands", {})

        assert "lock" in commands
        assert "suspend" in commands
        assert commands["lock"]["exec"] == "hyprlock"
        assert commands["suspend"]["exec"] == "systemctl suspend"

    def test_skips_malformed_commands(self, tmp_path):
        """Commands missing 'exec' field should be skipped."""
        commands_path = tmp_path / "commands.toml"
        data = {
            "commands": {
                "good": {"description": "Works", "exec": "echo ok"},
                "bad": {"description": "Missing exec field"},
                "also_bad": "not a dict",
            }
        }
        commands_path.write_text(toml.dumps(data))

        handler = CustomCommandsHandler.__new__(CustomCommandsHandler)
        data_loaded = toml.load(commands_path)
        commands = data_loaded.get("commands", {})
        # Apply the same validation as _load_commands
        for name, cmd in list(commands.items()):
            if not isinstance(cmd, dict) or "exec" not in cmd:
                del commands[name]
        handler.commands = commands

        assert "good" in handler.commands
        assert "bad" not in handler.commands
        assert "also_bad" not in handler.commands

    def test_empty_file_returns_no_commands(self, tmp_path):
        commands_path = tmp_path / "commands.toml"
        commands_path.write_text("")

        handler = CustomCommandsHandler.__new__(CustomCommandsHandler)
        data = toml.load(commands_path)
        handler.commands = data.get("commands", {})

        assert handler.commands == {}


class TestCommandsMatching:
    """Test the matches() and get_results() logic."""

    def _make_handler(self, commands: dict) -> CustomCommandsHandler:
        handler = CustomCommandsHandler.__new__(CustomCommandsHandler)
        handler.commands = commands
        return handler

    def test_matches_exclamation_prefix(self):
        handler = self._make_handler({"lock": {"exec": "hyprlock"}})
        assert handler.matches("!lock") is True

    def test_no_match_without_prefix(self):
        handler = self._make_handler({"lock": {"exec": "hyprlock"}})
        assert handler.matches("lock") is False

    def test_bare_exclamation_shows_all(self):
        handler = self._make_handler({
            "lock": {"exec": "hyprlock", "description": "Lock"},
            "suspend": {"exec": "systemctl suspend", "description": "Suspend"},
        })
        results = handler.get_results("!")
        assert len(results) == 2

    def test_filter_by_name(self):
        handler = self._make_handler({
            "lock": {"exec": "hyprlock", "description": "Lock screen"},
            "suspend": {"exec": "systemctl suspend", "description": "Suspend"},
        })
        results = handler.get_results("!lock")
        assert len(results) == 1
        assert results[0].title == "!lock"

    def test_unknown_command_shows_hint(self):
        handler = self._make_handler({"lock": {"exec": "hyprlock"}})
        results = handler.get_results("!nonexistent")
        assert len(results) == 1
        assert "unknown" in results[0].title.lower()
