"""Qt-free transmit-history model for the command input.

The :class:`TxHistory` keeps an ordered, consecutive-duplicate-free record of the
commands the user has sent, and exposes shell-like Up/Down navigation.  It has no
Qt dependency so it can be unit tested in isolation.
"""

from __future__ import annotations

#: Default maximum number of commands retained in the history.
DEFAULT_HISTORY_SIZE: int = 100


class TxHistory:
    """A bounded, consecutive-duplicate-free record of sent commands.

    Commands are normalised to ``strip()`` text.  Empty (or whitespace-only)
    commands are ignored, and sending the *same* command twice in a row does not
    create a second entry, so Up/Down never shows a repeated line.

    Navigation keeps a pointer either at the newest command or at the "live"
    input (``None``).  Calling :meth:`previous` moves backwards, :meth:`next`
    moves forwards again and finally returns ``None`` to signal "back to the
    live input".
    """

    def __init__(self, max_size: int = DEFAULT_HISTORY_SIZE) -> None:
        self._max_size = max(0, int(max_size))
        self._entries: list[str] = []
        #: Navigation pointer; ``None`` means "at the live input" (not navigating).
        self._index: int | None = None

    def __len__(self) -> int:
        """The number of commands currently stored."""
        return len(self._entries)

    def __bool__(self) -> bool:
        """``True`` when at least one command has been recorded."""
        return bool(self._entries)

    def __getitem__(self, index: int) -> str:
        return self._entries[index]

    def add(self, command: str) -> bool:
        """Record a sent *command*.

        Empty/whitespace text is ignored.  A command identical to the most
        recent entry is *not* re-added (which avoids consecutive duplicates in
        the history).  Returns ``True`` when the command was actually stored.
        """
        text = command.strip()
        if not text:
            return False
        if self._entries and self._entries[-1] == text:
            # Already the newest entry; keep its position and stop navigating.
            self._index = None
            return False
        self._entries.append(text)
        if self._max_size and len(self._entries) > self._max_size:
            del self._entries[: len(self._entries) - self._max_size]
        self._index = None
        return True

    def last(self) -> str | None:
        """Return the most recent command, or ``None`` when empty."""
        return self._entries[-1] if self._entries else None

    def reset(self) -> None:
        """Move the navigation pointer back to the live input."""
        self._index = None

    def previous(self) -> str | None:
        """Walk toward older commands and return the command at that point.

        The first call returns the newest command; repeated calls walk back
        until the oldest entry, which is then returned repeatedly.
        """
        if not self._entries:
            return None
        if self._index is None:
            self._index = len(self._entries) - 1
        elif self._index > 0:
            self._index -= 1
        return self._entries[self._index]

    def next(self) -> str | None:
        """Walk toward newer commands.

        Returns the next command, or ``None`` once past the newest entry, which
        the caller should treat as "return to the live input".
        """
        if not self._entries or self._index is None:
            return None
        self._index += 1
        if self._index >= len(self._entries):
            self._index = None
            return None
        return self._entries[self._index]
