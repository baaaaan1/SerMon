"""Shared serial line-ending definitions and RX stream parsing."""

from __future__ import annotations

import codecs
from dataclasses import dataclass


@dataclass(frozen=True)
class LineEndingMode:
    """Wire suffix and receive delimiter for one UI mode."""

    key: str
    label: str
    tx_suffix: bytes
    rx_delimiter: str | None


@dataclass(frozen=True)
class ParsedFragment:
    """Decoded display text plus whether it closes the current RX record."""

    text: str
    complete: bool


LINE_ENDING_MODES = (
    LineEndingMode("none", "No line ending", b"", None),
    LineEndingMode("lf", "LF (\\n)", b"\n", "\n"),
    LineEndingMode("cr", "CR (\\r)", b"\r", "\r"),
    LineEndingMode("crlf", "CRLF (\\r\\n)", b"\r\n", "\r\n"),
)
LINE_ENDING_BY_KEY = {mode.key: mode for mode in LINE_ENDING_MODES}
DEFAULT_LINE_ENDING = "crlf"
MAX_PENDING_CHARS = 64 * 1024


class SerialTextParser:
    """Incrementally decode RX bytes and split configured logical records."""

    def __init__(
        self,
        mode: str = DEFAULT_LINE_ENDING,
        max_pending_chars: int = MAX_PENDING_CHARS,
    ) -> None:
        if max_pending_chars < 1:
            raise ValueError("max_pending_chars must be positive")
        self._max_pending_chars = max_pending_chars
        self._mode = self._get_mode(mode)
        self._pending = ""
        self._display_cr = False
        self._decoder = self._new_decoder()

    @property
    def mode(self) -> LineEndingMode:
        return self._mode

    def set_mode(self, mode: str) -> None:
        """Select a mode and discard any decoder/parser state."""
        self._mode = self._get_mode(mode)
        self.reset()

    def feed(self, data: bytes) -> list[ParsedFragment]:
        """Decode a raw chunk and return text fragments ready for display."""
        text = self._decoder.decode(data, final=False)
        delimiter = self._mode.rx_delimiter
        if delimiter is None:
            text = self._display_text(text)
            return [ParsedFragment(text, False)] if text else []

        self._pending += text
        parts = self._pending.split(delimiter)
        self._pending = parts.pop()
        fragments = [
            ParsedFragment(self._display_text(part + delimiter), True)
            for part in parts
        ]

        if len(self._pending) > self._max_pending_chars:
            keep = self._delimiter_prefix_length(self._pending, delimiter)
            if keep:
                fragments.append(ParsedFragment(
                    self._display_text(self._pending[:-keep]), False))
                self._pending = self._pending[-keep:]
            else:
                fragments.append(ParsedFragment(
                    self._display_text(self._pending), False))
                self._pending = ""
        return fragments

    def flush(self) -> str:
        """Return pending decoded text and reset state while retaining mode."""
        tail = self._decoder.decode(b"", final=True)
        text = self._display_text(self._pending + tail)
        self.reset()
        return text

    def reset(self) -> None:
        """Discard all pending input while retaining the selected mode."""
        self._pending = ""
        self._display_cr = False
        self._decoder = self._new_decoder()

    def _display_text(self, text: str) -> str:
        """Normalize display newlines, including CRLF split across chunks."""
        if not text:
            return ""
        if self._display_cr and text.startswith("\n"):
            text = text[1:]
        self._display_cr = text.endswith("\r")
        return text.replace("\r\n", "\n").replace("\r", "\n")

    @staticmethod
    def _new_decoder():
        return codecs.getincrementaldecoder("utf-8")("replace")

    @staticmethod
    def _get_mode(key: str) -> LineEndingMode:
        try:
            return LINE_ENDING_BY_KEY[key]
        except KeyError as exc:
            raise ValueError("unknown line-ending mode: %s" % key) from exc

    @staticmethod
    def _delimiter_prefix_length(text: str, delimiter: str) -> int:
        """Return the longest trailing partial delimiter in ``text``."""
        max_length = min(len(text), len(delimiter) - 1)
        for length in range(max_length, 0, -1):
            if text.endswith(delimiter[:length]):
                return length
        return 0
