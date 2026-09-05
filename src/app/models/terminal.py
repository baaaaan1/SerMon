"""Qt-free view-model for the serial terminal display.

The :class:`TerminalViewModel` owns the *display logic* for the terminal: how a
parsed event becomes a line of text, optional timestamps, session/EOF markers and
the transmit line ending.  It is deliberately free of any Qt dependency so it can
be unit tested without a running ``QApplication``.

Byte *counting* is intentionally **not** duplicated here -- the application
already tracks cumulative RX/TX in :class:`~app.state.AppState`, so this model
only renders content and produces the line-ending byte sequence.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from serial_engine.protocols import ParsedEvent
from services.formatter import format_ascii, make_timestamp

#: Transmit end-of-line choices exposed in the UI (order defines the combo).
LINE_ENDINGS: tuple[str, ...] = ("None", "LF", "CR", "CRLF")

#: Byte sequence emitted for each transmit line-ending option.
_LINE_ENDING_BYTES: dict[str, bytes] = {
    "LF": b"\n",
    "CRLF": b"\r\n",
    "CR": b"\r",
    "None": b"",
}

#: Default scrollback size in lines (``0`` means unlimited).
DEFAULT_MAX_LINES: int = 5000

#: Scrollback limits offered in the UI (``0`` is shown as "Unlimited").
SCROLLBACK_LIMITS: tuple[int, ...] = (500, 1000, 5000, 10000, 50000, 0)


@dataclass
class TerminalOptions:
    """User-facing terminal display/behaviour options.

    A single mutable instance is shared between the view-model and the widgets,
    so toggling a checkbox simply mutates this object and the terminal follows.
    """

    show_timestamp: bool = True
    autoscroll: bool = True
    clear_on_connect: bool = False
    show_flow_markers: bool = True
    show_eof_marker: bool = True
    line_ending: str = "LF"
    #: Prefix each data line with an ``RX`` / ``TX`` direction label.
    show_rx_tx: bool = True
    #: Wrap long lines to the widget width instead of scrolling horizontally.
    word_wrap: bool = True
    #: Maximum number of lines kept in the buffer (``0`` = unlimited).
    max_lines: int = DEFAULT_MAX_LINES


class TerminalViewModel:
    """Turn parsed events into terminal text, honouring display options.

    The model accumulates rendered lines in an internal buffer (used by tests and
    by a potential "copy all" feature) and returns each new line so a widget can
    append it immediately.  Byte counters live elsewhere, in ``AppState``.
    """

    def __init__(self, options: TerminalOptions | None = None) -> None:
        self.options = options or TerminalOptions()
        self._lines: list[str] = []

    @property
    def plain_text(self) -> str:
        """The full accumulated terminal text (one entry per line)."""
        return "".join(self._lines)

    @property
    def lines(self) -> list[str]:
        """A copy of the accumulated rendered lines (for re-rendering on theme change)."""
        return list(self._lines)

    def line_ending_bytes(self) -> bytes:
        """Return the byte sequence for the configured transmit line ending."""
        return _LINE_ENDING_BYTES.get(self.options.line_ending, b"\n")

    def append_event(self, event: ParsedEvent) -> str:
        """Render *event* and append it to the buffer, returning the new line."""
        line = self._render_line(self._event_body(event), "RX")
        self._lines.append(line)
        self._trim()
        return line

    def append_events(self, events: Iterable[ParsedEvent]) -> list[str]:
        """Render every *event*, append them to the buffer and return the kept lines.

        Rendering the whole batch up-front let a widget inject many lines in a
        single pass, which keeps the UI responsive under high RX load.  Only the
        lines that survive the scrollback limit are returned so the widget inserts
        exactly what the buffer retains.
        """
        rendered = [self._render_line(self._event_body(ev), "RX") for ev in events]
        return self._stash(rendered)

    def append_tx(self, text: str) -> str:
        """Render a transmit line and append it to the buffer, returning it."""
        line = self._render_line(text, "TX")
        self._lines.append(line)
        self._trim()
        return line

    def set_max_lines(self, limit: int) -> None:
        """Change the scrollback limit and trim the buffer to the new size."""
        self.options.max_lines = max(0, int(limit))
        self._trim()

    def on_connect(self) -> str | None:
        """Handle a connection opening.

        When ``clear_on_connect`` is enabled the buffer is emptied first.  When
        flow markers are enabled a session marker is appended and returned so the
        widget can render it.  Returns ``None`` when nothing should be drawn.
        """
        if self.options.clear_on_connect:
            self._lines.clear()
        if not self.options.show_flow_markers:
            return None
        marker = self._render_system_line("--- Connected ---")
        self._lines.append(marker)
        self._trim()
        return marker

    def on_disconnect(self) -> str | None:
        """Handle a connection closing, emitting an EOF marker when enabled."""
        if not self.options.show_eof_marker:
            return None
        marker = self._render_system_line("--- Disconnected (EOF) ---")
        self._lines.append(marker)
        self._trim()
        return marker

    def clear(self) -> None:
        """Empty the accumulated buffer (does not touch byte counters)."""
        self._lines.clear()

    def _stash(self, rendered: list[str]) -> list[str]:
        """Append *rendered* lines, trim, and return the lines still in the buffer."""
        if not rendered:
            return []
        self._lines.extend(rendered)
        self._trim()
        limit = self.options.max_lines
        return rendered[-limit:] if limit else rendered

    def _trim(self) -> None:
        """Drop the oldest lines beyond :attr:`TerminalOptions.max_lines`."""
        limit = self.options.max_lines
        if limit and len(self._lines) > limit:
            del self._lines[: len(self._lines) - limit]

    # -- Rendering helpers ---------------------------------------------------

    def _event_body(self, event: ParsedEvent) -> str:
        payload = event.payload
        if isinstance(payload, str):
            return payload
        if isinstance(payload, (bytes, bytearray)):
            return format_ascii(bytes(payload))
        return str(payload)

    def _render_line(self, body: str, direction: str | None = None) -> str:
        prefix = f"[{make_timestamp()}] " if self.options.show_timestamp else ""
        if direction and self.options.show_rx_tx:
            prefix += f"{direction}  "
        return f"{prefix}{body}\n"

    def _render_system_line(self, text: str) -> str:
        return self._render_line(text)
