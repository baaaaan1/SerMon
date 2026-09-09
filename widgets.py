"""Reusable neumorphism widgets.

The soft "dual shadow" (light top-left + dark bottom-right) is painted directly
in ``paintEvent`` because Qt's QSS does not support ``box-shadow``.  Buttons are
rendered as soft, flat pills that sit *carved into* the surface (recessed), so
nothing pops out with a hard 3D shadow.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QRectF, QSize, QDateTime
from PySide6.QtGui import (
    QColor, QPainter, QPainterPath, QPen, QBrush, QLinearGradient, QFont,
    QTextCursor, QTextCharFormat,
)
from PySide6.QtWidgets import QAbstractButton, QFrame, QPlainTextEdit

from theme import PALETTE, UI_FONT, TERM_FONT, TERM_SIZE


# --------------------------------------------------------------------------- #
#  Raised / recessed controls
# --------------------------------------------------------------------------- #
class NeumorphicButton(QAbstractButton):
    """A soft, flat neumorphic button carved into the surface (recessed)."""

    def __init__(self, text: str = "", radius: int = 14, accent: bool = False,
                 toggle: bool = False, parent=None):
        super().__init__(parent)
        self._radius = radius
        self._accent = accent
        self._face = QColor(PALETTE["surface"])
        self.setText(text)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setCheckable(toggle)
        self.setMinimumHeight(38)
        self.setFont(QFont(UI_FONT, 10))

    def sizeHint(self) -> QSize:
        w = self.fontMetrics().horizontalAdvance(self.text()) + 40
        return QSize(max(w, 62), 42)

    def _active(self) -> bool:
        return self.isCheckable() and self.isChecked()

    def paintEvent(self, event) -> None:   # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        pressed = self.isDown() or self._active()
        hover = self.underMouse() and self.isEnabled()
        m = 2.0
        rect = QRectF(self.rect()).adjusted(m, m, -m, -m)
        r = float(self._radius)
        path = QPainterPath()
        path.addRoundedRect(rect, r, r)

        # carved-in face (flat / recessed neumorphism: no outer shadow)
        face = QColor(self._face)
        if pressed:
            face = self._shade(face, 14, toward_dark=True)
        elif hover:
            face = self._shade(face, 10, toward_dark=False)

        p.setPen(Qt.NoPen)
        p.setClipPath(path)
        p.fillPath(path, QBrush(face))

        # inner shadow from the top edge -> looks carved / sunken in
        g_top = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        top_a = 95 if pressed else 60
        g_top.setColorAt(0.0, QColor(0, 0, 0, top_a))
        g_top.setColorAt(0.32, QColor(0, 0, 0, 0))
        g_top.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.fillRect(rect, QBrush(g_top))

        # inner highlight along the bottom edge -> catches the light
        g_bot = QLinearGradient(rect.bottomLeft(), rect.topLeft())
        bot_a = 42 if pressed else 28
        g_bot.setColorAt(0.0, QColor(255, 255, 255, bot_a))
        g_bot.setColorAt(0.34, QColor(255, 255, 255, 0))
        p.fillRect(rect, QBrush(g_bot))

        p.setClipping(False)

        # label
        col = QColor(PALETTE["text"] if self.isEnabled() else PALETTE["text_muted"])
        if self.isEnabled() and (self._accent or self._active()):
            col = QColor(PALETTE["accent"])
        p.setPen(col)
        p.setFont(self.font())
        p.drawText(rect, Qt.AlignCenter, self.text())

    @staticmethod
    def _shade(c: QColor, amt: int, toward_dark: bool) -> QColor:
        if toward_dark:
            return QColor(max(0, c.red() - amt), max(0, c.green() - amt),
                          max(0, c.blue() - amt))
        return QColor(min(255, c.red() + amt), min(255, c.green() + amt),
                      min(255, c.blue() + amt))
class NeumorphicFrame(QFrame):
    """A recessed (inset) container, e.g. the terminal and the toolbar trays."""

    def __init__(self, radius: int = 16, parent=None):
        super().__init__(parent)
        self._radius = radius
        self._fill = QColor(PALETTE["surface_dark"])

    def paintEvent(self, event) -> None:   # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        r = float(self._radius)
        p.setPen(Qt.NoPen)
        p.setBrush(self._fill)
        p.drawRoundedRect(rect, r, r)
        # inner edge highlights -> recessed / carved look
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(*PALETTE["shadow_dark"]).lighter(45), 1.6))
        p.drawRoundedRect(rect.adjusted(1, 1, -1, -1), r, r)
        p.setPen(QPen(QColor(*PALETTE["shadow_light"]), 1.2))
        p.drawRoundedRect(rect.adjusted(2, 2, -2, -2), r, r)


class TerminalView(QPlainTextEdit):
    """Read-only terminal editor with auto-scroll and per-kind colouring."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("terminal")
        self.setReadOnly(True)
        self.setFrameStyle(QFrame.NoFrame)
        self.setFont(QFont(TERM_FONT, TERM_SIZE))
        self.setMaximumBlockCount(20000)
        self._follow = True
        self._timestamps = False
        self._colors = {
            "rx":  QColor(PALETTE["terminal_rx"]),
            "tx":  QColor(PALETTE["terminal_tx"]),
            "sys": QColor(PALETTE["terminal_sys"]),
        }
        self.verticalScrollBar().valueChanged.connect(self._on_scroll)

    def set_follow(self, follow: bool) -> None:
        self._follow = bool(follow)
        if follow:
            self._scroll_bottom()

    def clear_terminal(self) -> None:
        self.clear()

    def set_timestamps(self, enabled: bool) -> None:
        self._timestamps = bool(enabled)

    def append_text(self, text: str, kind: str = "rx") -> None:
        """Append coloured text.  ``kind`` is rx / tx / sys."""
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.End)
        if self._timestamps and kind in ("rx", "tx"):
            ts_fmt = QTextCharFormat()
            ts_fmt.setForeground(self._colors["sys"])
            ts = QDateTime.currentDateTime().toString("HH:mm:ss.zzz")
            cursor.insertText("[%s] " % ts, ts_fmt)
        fmt = QTextCharFormat()
        fmt.setForeground(self._colors.get(kind, self._colors["rx"]))
        if kind == "tx":
            fmt.setFontWeight(700)
        cursor.insertText(text, fmt)
        if self._follow:
            self._scroll_bottom()

    def _scroll_bottom(self) -> None:
        bar = self.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _on_scroll(self, value: int) -> None:
        bar = self.verticalScrollBar()
        # stop auto-following once the user scrolls away from the bottom
        self._follow = value >= bar.maximum() - 1

