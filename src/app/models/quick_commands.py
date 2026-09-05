"""Qt-free model backing the "Quick Commands" preset list.

The :class:`QuickCommandsModel` owns the *data* (an ordered list of transmit
presets) and exposes it through small mutators.  It has no Qt dependency so it
can be unit tested on its own, and later persisted/reused by the UI.
"""

from __future__ import annotations

#: Preset send-lines shown the first time the application runs.
DEFAULT_COMMANDS: tuple[str, ...] = (
    "AT",
    "ATI",
    "AT+GMR",
    "AT+RST",
    "?",
    "help",
    "start",
    "stop",
)


class QuickCommandsModel:
    """A simple, editable collection of preset transmit strings."""

    def __init__(self, commands: list[str] | None = None) -> None:
        self._commands = list(commands) if commands is not None else list(DEFAULT_COMMANDS)

    @property
    def commands(self) -> list[str]:
        """A shallow copy of the current command list."""
        return list(self._commands)

    def __len__(self) -> int:
        return len(self._commands)

    def __getitem__(self, index: int) -> str:
        return self._commands[index]

    def add(self, command: str) -> None:
        """Append *command* (trimmed).

        An empty string is retained so the UI can present an editable slot the
        user fills in; an all-whitespace command is normalised to ``""``.
        """
        self._commands.append(command.strip())

    def set_command(self, index: int, command: str) -> None:
        """Replace the command at *index* with *command* (trimmed)."""
        if 0 <= index < len(self._commands):
            self._commands[index] = command.strip()

    def remove(self, index: int) -> None:
        """Drop the command at *index*; no-op when out of range."""
        if 0 <= index < len(self._commands):
            del self._commands[index]

    def clear(self) -> None:
        """Remove every command."""
        self._commands.clear()
