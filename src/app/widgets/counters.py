"""Compact RX/TX byte counter widget for the status bar."""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from ..theme import get_theme_manager


class ByteCounter(QWidget):
    """Display cumulative received/transmitted byte counts.

    The ``RX``/``TX`` labels are tinted with the theme's direction roles
    (``theme.rx`` / ``theme.tx``) so the counters read as data direction rather
    than decoration, and repaint when the theme changes.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rx_label = QLabel("RX: 0")
        self._tx_label = QLabel("TX: 0")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._rx_label)
        layout.addWidget(self._tx_label)
        get_theme_manager().theme_changed.connect(self._on_theme_changed)
        self._on_theme_changed(get_theme_manager().theme)

    def set_counts(self, rx: int, tx: int) -> None:
        """Update the displayed RX/TX counts."""
        self._rx_label.setText(f"RX: {rx}")
        self._tx_label.setText(f"TX: {tx}")

    def _on_theme_changed(self, _theme) -> None:
        """Re-apply the direction colours after a theme switch."""
        theme = get_theme_manager().theme
        self._rx_label.setStyleSheet(f"color: {theme.rx}; font-weight: 600;")
        self._tx_label.setStyleSheet(f"color: {theme.tx}; font-weight: 600;")

    @property
    def rx_text(self) -> str:
        """Current RX label text (used by tests)."""
        return self._rx_label.text()

    @property
    def tx_text(self) -> str:
        """Current TX label text (used by tests)."""
        return self._tx_label.text()
