"""Protocol parser extension point.

A :class:`ProtocolParser` transforms raw byte chunks into higher level events.
The rest of the application is written against this interface, so adding a new
protocol is a purely additive change that never requires a UI rewrite.
"""

from __future__ import annotations

from .base import ParsedEvent, ProtocolParser
from .hex import HexParser
from .line import LineParser
from .registry import ProtocolRegistry, register, registry

__all__ = [
    "HexParser",
    "LineParser",
    "ParsedEvent",
    "ProtocolParser",
    "ProtocolRegistry",
    "register",
    "registry",
]
