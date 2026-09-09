"""Custom frameless title bar for the Serial Monitor window.

Switching the window to ``Qt.FramelessWindowHint`` removes the native caption,
so this widget supplies a themed (``#2b2e33``) title bar with the classic
minimise / maximise / close controls, plus native drag and double-click
maximise/restore.

Drag uses :meth:`QWindow.startSystemMove` so Aero Snap and the maximise-by-
dragging-to-the-top-edge behaviour keep working.  Window edges are resized in
``MainWindow`` (see ``eventFilter``), not here.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from theme import PALETTE


class FramelessTitleBar(QWidget):
    """A draggable, dark title bar that mimics the removed native caption."""

    def __init__(self, window: QWidget, title: str = "") -> None:
        super().__init__(window)
        self._window = window
        self.title = title
        self.setObjectName("titleBar")
        self.setFixedHeight(32)
        self.setFocusPolicy(Qt.NoFocus)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 0, 0)
        lay.setSpacing(0)

        self.lbl_title = QLabel(title)
        self.lbl_title.setStyleSheet(
            "color: %s; background: transparent; font-weight: 600;" % PALETTE["text"])
        lay.addWidget(self.lbl_title)
        lay.addStretch(1)

        self.btn_min = self._control("–", "tbMin")
        self.btn_max = self._control("□", "tbMax")
        self.btn_close = self._control("×", "tbClose")

        self.btn_min.clicked.connect(lambda: self._window.showMinimized())
        self.btn_max.clicked.connect(self._toggle_max)
        self.btn_close.clicked.connect(self._window.close)

        lay.addWidget(self.btn_min)
        lay.addWidget(self.btn_max)
        lay.addWidget(self.btn_close)

    @staticmethod
    def _control(text: str, object_name: str) -> QPushButton:
        btn = QPushButton(text)
        btn.setObjectName(object_name)
        btn.setFocusPolicy(Qt.NoFocus)
        btn.setFixedSize(46, 32)
        return btn

    def _toggle_max(self) -> None:
        if self._window.isMaximized():
            self._window.showNormal()
        else:
            self._window.showMaximized()

    def update_state(self, maximized: bool) -> None:
        """Sync the maximise/restore glyph (e.g. after an Aero Snap maximise)."""
        self.btn_max.setText("❐" if maximized else "□")

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
