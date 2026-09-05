"""Parsing for in-band DTR/RTS line-control commands.

The serial monitor lets the user drive the generic RS-232 control lines (DTR and
RTS) both from the sidebar toggles *and* by typing ``DTR ON`` / ``RTS OFF`` into
the TX input.  Such commands never transmit data: they are intercepted and
applied directly to the line before any bytes are written.

This module is Qt-free and contains no hardware assumptions -- ``DTR`` and
``RTS`` are treated as opaque line names, not as "reset the MCU" or anything
chip-specific.  A command is always exactly two tokens: a line name and an
ON/OFF state.
"""

from __future__ import annotations

from dataclasses import dataclass

#: The two RS-232 control lines the monitor can drive generically.
SUPPORTED_LINE_NAMES: tuple[str, ...] = ("dtr", "rts")


@dataclass(frozen=True)
class LineControlCommand:
    """A parsed ``DTR ON|OFF`` / ``RTS ON|OFF`` command.

    ``line`` is normalised to lowercase (``"dtr"`` or ``"rts"``) so callers can
    use it directly as a session attribute name; ``enabled`` is the requested
    line level (``True`` = asserted, ``False`` = deasserted).
    """

    line: str
    enabled: bool


def parse_line_control_command(text: str) -> LineControlCommand | None:
    """Parse *text* as a DTR/RTS command.

    The grammar is deliberately whitespace- and case-tolerant (``DTR ON``,
    ``rts  off``, ``Rts Off`` are all accepted).  Returns a
    :class:`LineControlCommand` when *text* is a valid line-control command and
    only then; otherwise (including any extra trailing tokens) ``None`` is
    returned so the caller falls back to normal transmission.
    """
    parts = text.strip().split(None, 1)
    if len(parts) != 2:
        return None
    line, state = parts[0].lower(), parts[1].strip().lower()
    if line not in SUPPORTED_LINE_NAMES:
        return None
    if state == "on":
        enabled = True
    elif state == "off":
        enabled = False
    else:
        return None
    return LineControlCommand(line=line, enabled=enabled)
