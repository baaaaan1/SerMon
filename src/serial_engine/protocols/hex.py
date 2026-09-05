"""Hexadecimal protocol parser.

Emits each chunk of raw bytes as an uppercase, space-separated hex string, so a
terminal can display the raw byte stream in a readable, byte-oriented form.
"""

from __future__ import annotations

from .base import ParsedEvent, ProtocolParser
from .registry import register


@register("hex")
class HexParser(ProtocolParser):
    """Emit incoming bytes as a ``"hex"`` event per chunk."""

    name = "hex"

    def feed(self, data: bytes) -> list[ParsedEvent]:
        if not data:
            return []
        return [ParsedEvent(type="hex", payload=data.hex(" ").upper(), raw=data)]
