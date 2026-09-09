"""Custom frameless title bar for the Serial Monitor window.

Switching the window to ``Qt.FramelessWindowHint`` removes the native caption,
so this widget supplies a themed (``#2b2e33``) title bar with the classic
minimise / maximise / close controls, plus native drag and double-click
maximise/restore.

Drag uses :meth:`QWindow.startSystemMove` so Aero Snap and the maximise-by-
dragging-to-the-top-edge behaviour keep working.  Window edges are resized in
``MainWindow`` (see ``eventFilter``), not here.

The window-control glyphs are painted as crisp vector icons (24x24 box, ~1.8px
pen, centred - not baseline-aligned) so they stay proportional to the rest of
the UI instead of relying on a font glyph.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from theme import PALETTE


class WindowControlButton(QPushButton):
    """A title-bar button that paints its own vector icon (min/max/close)."""

    # ---- mudah diubah: ukuran ikon window-control -------------------------
    # GLYPH = setengah-ukuran glyph (2*GLYPH px total). Kecilkan -> angka kecil.
    # PEN   = ketebalan garis ikon.
    GLYPH = 4.5
    PEN   = 1.8

    _OBJ = {"min": "tbMin", "max": "tbMax", "restore": "tbMax", "close": "tbClose"}

    def __init__(self, icon: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._icon = icon
        self._maximized = False
        self.setObjectName(self._OBJ[icon])
        self.setFixedSize(46, 34)
        self.setFocusPolicy(Qt.NoFocus)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip({
            "min": "Minimize", "max": "Maximize",
            "restore": "Restore", "close": "Close",
        }[icon])

    def set_restore(self, maximized: bool) -> None:
        """Toggle the maximise button between the maximise / restore glyphs."""
        self._maximized = bool(maximized)

    def paintEvent(self, event) -> None:   # noqa: N802
        super().paintEvent(event)          # QSS background + hover state
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        hover = self.underMouse() and self.isEnabled()

        if self.objectName() == "tbClose":
            col = QColor("#ffffff") if hover else QColor(PALETTE["text_muted"])
        else:
            col = QColor(PALETTE["text"]) if hover else QColor(PALETTE["text_muted"])

        pen = QPen(col, self.PEN)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)

        cx = self.rect().center().x()
        cy = self.rect().center().y()

        if self._icon == "min":
            p.drawLine(cx - self.GLYPH, cy, cx + self.GLYPH, cy)
        elif self._icon == "close":
            p.drawLine(cx - self.GLYPH, cy - self.GLYPH, cx + self.GLYPH, cy + self.GLYPH)
            p.drawLine(cx - self.GLYPH, cy + self.GLYPH, cx + self.GLYPH, cy - self.GLYPH)
        elif self._maximized:               # restore: two overlapping squares
            r, off = self.GLYPH - 3, 3
            p.drawRect(QRectF(cx - r - off, cy - r - off, 2 * r, 2 * r))
            p.drawRect(QRectF(cx - r + off, cy - r + off, 2 * r, 2 * r))
        else:                               # maximise: single square
            p.drawRect(QRectF(cx - self.GLYPH, cy - self.GLYPH, 2 * self.GLYPH, 2 * self.GLYPH))


class FramelessTitleBar(QWidget):
    """A draggable, dark title bar that mimics the removed native caption."""

    def __init__(self, window: QWidget, title: str = "") -> None:
        super().__init__(window)
        self._window = window
        self.title = title
        self.setObjectName("titleBar")
        self.setFixedHeight(34)
        self.setFocusPolicy(Qt.NoFocus)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 0, 0, 0)
        lay.setSpacing(0)

        self.lbl_icon = QLabel(self)
        self.lbl_icon.setFixedSize(22, 22)
        self.lbl_icon.setPixmap(window.windowIcon().pixmap(18, 18))
        self.lbl_icon.setToolTip(title)
        lay.addWidget(self.lbl_icon)
        lay.addSpacing(7)

        self.lbl_title = QLabel(title)
        self.lbl_title.setStyleSheet(
            "color: %s; background: transparent; font-size: 15px; font-weight: 600;"
            % PALETTE["text"])
        lay.addWidget(self.lbl_title)
        lay.addStretch(1)

        self.btn_min = WindowControlButton("min")
        self.btn_max = WindowControlButton("max")
        self.btn_close = WindowControlButton("close")

        self.btn_min.clicked.connect(lambda: self._window.showMinimized())
        self.btn_max.clicked.connect(self._toggle_max)
        self.btn_close.clicked.connect(self._window.close)

        lay.addWidget(self.btn_min)
        lay.addWidget(self.btn_max)
        lay.addWidget(self.btn_close)

    def _toggle_max(self) -> None:
        if self._window.isMaximized():
            self._window.showNormal()
        else:
            self._window.showMaximized()

    def update_state(self, maximized: bool) -> None:
        """Sync the maximise/restore icon (e.g. after an Aero Snap maximise)."""
        self.btn_max.set_restore(maximized)

    # ------------------------------------------------------------- dragging #
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            handle = self._window.windowHandle()
            if handle is not None:
                handle.startSystemMove()
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._toggle_max()
        super().mouseDoubleClickEvent(event)
