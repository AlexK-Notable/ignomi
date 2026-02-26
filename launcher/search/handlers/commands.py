"""
Custom Commands Handler - User-defined command aliases.

Reads command definitions from data/commands.toml and matches
queries starting with "!" prefix.

Example commands.toml:
    [commands.lock]
    description = "Lock screen"
    exec = "hyprlock"
    icon = "system-lock-screen"

    [commands.suspend]
    description = "Suspend system"
    exec = "systemctl suspend"
    icon = "system-suspend"

Usage: !lock, !suspend, etc.
"""

import subprocess
from pathlib import Path

import toml
from loguru import logger
from search.router import ResultItem


class CustomCommandsHandler:
    """Execute user-defined commands via '!' prefix."""

    name = "commands"
    priority = 300

    def __init__(self):
        self.commands = self._load_commands()

    def matches(self, query: str) -> bool:
        return query.strip().startswith("!")

    def get_results(self, query: str) -> list[ResultItem]:
        q = query.strip().lstrip("!").strip().lower()

        if not q:
            # Show all available commands
            return [
                self._command_to_result(name, cmd)
                for name, cmd in sorted(self.commands.items())
            ]

        # Filter commands matching query
        results = []
        for name, cmd in self.commands.items():
            if q in name.lower() or q in cmd.get("description", "").lower():
                results.append(self._command_to_result(name, cmd))

        if not results:
            return [ResultItem(
                title=f"Unknown command: !{q}",
                description="Type ! to see available commands",
                icon="dialog-question",
                result_type="command",
            )]

        return results

    def _command_to_result(self, name: str, cmd: dict) -> ResultItem:
        """Convert a command definition to a ResultItem."""
        return ResultItem(
            title=f"!{name}",
            description=cmd.get("description", ""),
            icon=cmd.get("icon", "utilities-terminal"),
            result_type="command",
            on_activate=lambda c=cmd: self._execute(c),
        )

    def _execute(self, cmd: dict):
        """Execute command and close launcher."""
        exec_str = cmd.get("exec", "")
        if exec_str:
            try:
                subprocess.Popen(
                    exec_str,
                    shell=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except Exception:
                logger.exception(f"Failed to execute command: {exec_str}")

        from utils.helpers import close_launcher
        close_launcher()

    def _load_commands(self) -> dict:
        """Load commands from data/commands.toml."""
        commands_path = Path(__file__).parent.parent.parent / "data" / "commands.toml"
        if not commands_path.exists():
            return {}

        try:
            data = toml.load(commands_path)
            commands = data.get("commands", {})
            # Validate entries
            for name, cmd in list(commands.items()):
                if not isinstance(cmd, dict) or "exec" not in cmd:
                    logger.warning(f"Skipping malformed command '{name}': missing 'exec' field")
                    del commands[name]
            return commands
        except Exception:
            logger.exception(f"Failed to load commands from {commands_path}")
            return {}
