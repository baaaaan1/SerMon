"""Line-oriented protocol parser.

Buffers incoming bytes and emits one :class:`ParsedEvent` per newline-delimited
line.  Lines that arrive split across several chunks are held in an internal
buffer and only emitted once a ``\\n`` (optionally preceded by ``\\r``) arrives.
"""

from __future__ import annotations

from .base import ParsedEvent, ProtocolParser
from .registry import register


@register("line")
class LineParser(ProtocolParser):
    """Accumulate bytes until a newline and emit each line as a ``"line"`` event."""

    name = "line"

    def __init__(self, *, encoding: str = "utf-8", errors: str = "replace") -> None:
        self._buffer = bytearray()
        self._encoding = encoding
        self._errors = errors

    def feed(self, data: bytes) -> list[ParsedEvent]:
        self._buffer.extend(data)
        events: list[ParsedEvent] = []
        while True:
            newline = self._buffer.find(b"\n")
            if newline == -1:
                break
            line = bytes(self._buffer[:newline])
            del self._buffer[: newline + 1]
            if line.endswith(b"\r"):
                line = line[:-1]
            events.append(
                ParsedEvent(
                    type="line",
                    payload=line.decode(self._encoding, errors=self._errors),
                    raw=line,
                )
            )
        return events

    def reset(self) -> None:
        """Drop any partially buffered line."""
        self._buffer.clear()
