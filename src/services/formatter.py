"""Formatting helpers for turning bytes into user-facing strings."""

from __future__ import annotations

from datetime import datetime, timezone


def format_hex(data: bytes, *, max_bytes: int | None = None) -> str:
    """Return an uppercase, space-separated hex representation of *data*."""
    if max_bytes is not None:
        data = data[:max_bytes]
    return data.hex(" ").upper()


def format_ascii(data: bytes) -> str:
    """Decode bytes to printable ASCII, replacing control chars with '.'."""
    return "".join(chr(b) if 32 <= b < 127 or b in (9, 10, 13) else "." for b in data)


def format_payload(data: bytes, *, hex: bool = True) -> str:
    """Format *data* either as hex or printable ASCII."""
    return format_hex(data) if hex else format_ascii(data)


def make_timestamp() -> str:
    """Return a millisecond-precision local time string for the log view."""
    return datetime.now(timezone.utc).astimezone().strftime("%H:%M:%S.%f")[:-3]
