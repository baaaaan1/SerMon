"""Base interface for protocol parsers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ParsedEvent:
    """A single parsed event produced by a protocol parser."""

    type: str
    payload: Any = None
    raw: bytes = b""
    timestamp: float = 0.0


class ProtocolParser(ABC):
    """Abstract protocol parser.

    Implementations receive raw bytes via :meth:`feed` and emit zero or more
    :class:`ParsedEvent` objects.  They should tolerate a :meth:`reset` call,
    which is used when reconnecting or switching protocols.
    """

    #: Stable identifier shown to users; subclasses should override.
    name: str = "raw"

    @abstractmethod
    def feed(self, data: bytes) -> list[ParsedEvent]:
        """Process a chunk of incoming bytes and return any complete events."""
        raise NotImplementedError

    def reset(self) -> None:
        """Clear internal buffering/parsing state (default: no-op)."""

    def __repr__(self) -> str:
        return f"<{type(self).__name__} name={self.name!r}>"
