"""Small status indicators for the connection state and RX/TX traffic.

* :class:`StatusDot` -- a coloured, glyph-marked circle showing the connection
  state.  Colour is always paired with a glyph and a tooltip/label so the state
  is never communicated by colour alone.
* :class:`ActivityIndicator` -- a pair of "RX"/"TX" dots that briefly blink
  whenever bytes are received/transmitted.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from ..theme import contrast_ratio, get_theme_manager

#: Connection state name -> semantic colour token (resolved from the active theme).
CONNECTION_ROLES: dict[str, str] = {
    "connected": "connected",
    "connecting": "warning",
    "busy": "warning",
    "reconnecting": "warning",
    "error": "error",
    "disconnected": "disconnected",
}

#: Connection state name -> tooltip / human label.
CONNECTION_LABELS: dict[str, str] = {
    "connected": "Connected",
    "connecting": "Connecting…",
    "busy": "Busy…",
    "reconnecting": "Reconnecting…",
    "error": "Error",
    "disconnected": "Disconnected",
}

#: Connection state name -> glyph shown inside the dot (an icon cue alongside colour).
CONNECTION_GLYPHS: dict[str, str] = {
    "connected": "●",
    "connecting": "◐",
    "busy": "◐",
    "reconnecting": "◐",
    "error": "✕",
    "disconnected": "○",
}

#: Dot diameter (px) -- sized so the glyph stays legible.
_DOT_SIZE = 18


def _glyph_color(fill: str) -> str:
    """Return black/white glyph colour with the best contrast on *fill*."""
    white, black = contrast_ratio(fill, "#ffffff"), contrast_ratio(fill, "#000000")
    return "#ffffff" if white >= black else "#000000"


class StatusDot(QLabel):
    """A coloured, glyph-marked circle indicating the connection state."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state = "disconnected"
        self.setObjectName("statusDot")
        self.setFixedSize(_DOT_SIZE, _DOT_SIZE)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.set_state("disconnected")
        get_theme_manager().theme_changed.connect(self._on_theme_changed)

    def set_state(self, state: str) -> None:
        """Paint the dot for *state* (one of :data:`CONNECTION_ROLES`)."""
        self._state = state
        self._paint()

    def _paint(self) -> None:
        theme = get_theme_manager().theme
        role = CONNECTION_ROLES.get(self._state, CONNECTION_ROLES["disconnected"])
        color = getattr(theme, role)
        glyph = CONNECTION_GLYPHS.get(self._state, CONNECTION_GLYPHS["disconnected"])
        label = CONNECTION_LABELS.get(self._state, CONNECTION_LABELS["disconnected"])
        fg = _glyph_color(color)
        self.setText(glyph)
        self.setStyleSheet(
            f"background-color: {color}; color: {fg}; font-weight: bold;"
            f" border-radius: {_DOT_SIZE // 2}px; border: 1px solid {theme.border};"
        )
        self.setToolTip(label)

    def _on_theme_changed(self, _theme) -> None:
        self._paint()


class _Blip(QLabel):
    """A labelled dot that brightens briefly when activity is detected."""

    FLASH_MS = 350

    def __init__(
        self,
        text: str,
        active_role: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(f"● {text}", parent)
        self._base = text
        self._active_role = active_role
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(self.FLASH_MS)
        self._timer.timeout.connect(self._dim)
        self._dim()
        get_theme_manager().theme_changed.connect(self._on_theme_changed)

    def _active_color(self) -> str:
        """Resolve this blip's active colour from the current theme."""
        return getattr(get_theme_manager().theme, self._active_role)

    def flash(self) -> None:
        """Brighten the dot until :data:`FLASH_MS` elapses."""
        self.setStyleSheet(f"color: {self._active_color()}; font-weight: bold;")
        self._timer.start()

    def _dim(self) -> None:
        self.setStyleSheet(f"color: {get_theme_manager().theme.blip_dim};")

    def _on_theme_changed(self, _theme) -> None:
        # A flash re-applies its bright colour when it times out; otherwise re-dim.
        if not self._timer.isActive():
            self._dim()

    @property
    def base_text(self) -> str:
        """The plain label (e.g. ``"RX"``) without the dot prefix."""
        return self._base


class ActivityIndicator(QWidget):
    """A compact RX/TX traffic indicator for the status bar."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rx = _Blip("RX", "rx")
        self._tx = _Blip("TX", "tx")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self._rx)
        layout.addWidget(self._tx)

    def rx_activity(self) -> None:
        """Signal that bytes were received."""
        self._rx.flash()

    def tx_activity(self) -> None:
        """Signal that bytes were transmitted."""
        self._tx.flash()

    @property
    def rx(self) -> _Blip:
        """The RX indicator label."""
        return self._rx

    @property
    def tx(self) -> _Blip:
        """The TX indicator label."""
        return self._tx
