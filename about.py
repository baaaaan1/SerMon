"""About panel for the Serial Monitor application.

A frameless, neumorphic dialog that mirrors the main window's dark soft-UI look.
It is opened directly from the menu bar ("About", F1) and shows the app version,
a short description, the highlighted feature set, the technology stack, and the
author / repository links.

The application metadata lives here (instead of in ``main.py``) so this module
never has to import ``main`` -- which would create a circular import, because
``main.py`` imports :class:`AboutDialog`.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget,
)

from theme import PALETTE, CONTROL_H, BUTTON_MIN_W
from widgets import NeumorphicButton


# --------------------------------------------------------------------------- #
#  Application metadata (single source of truth for the About panel)
# --------------------------------------------------------------------------- #
APP_NAME = "Serial Monitor"
APP_VERSION = "1.3.0"
APP_TAGLINE = (
    "A modern, functional Windows serial-port monitor wrapped in an elegant "
    "dark neumorphism (soft-UI) skin."
)
APP_AUTHOR = "baaaaan1"
APP_REPO = "https://github.com/baaaaan1/SerMon"
APP_ICON_PATH = Path(__file__).resolve().parent / "assets" / "app_icon.ico"

APP_DESCRIPTION = (
    "Serial Monitor is a lightweight desktop tool for talking to serial "
    "devices such as Arduino, ESP32, and other microcontrollers. Pick a port "
    "and a baud rate, press Connect, and watch incoming data stream into a "
    "colour-coded terminal while you type commands back. Auto-Reconnect keeps "
    "the link alive when a board resets, and the frameless neumorphic shell "
    "keeps everything easy on the eyes during long debugging sessions."
)

FEATURES = [
    "Neumorphism dark mode with code-painted soft shadows",
    "Custom frameless title bar (drag, Aero Snap, edge resize)",
    "Port + baud selection with one-click Refresh",
    "Connect / Disconnect plus a DTR toggle",
    "Auto-Reconnect and Auto-Clear on reconnect",
    "Colour-coded RX / TX / system terminal output",
    "Optional millisecond timestamps on every line (Ctrl+T)",
    "Shared TX/RX line-ending modes with chunk-safe parsing",
    "Saved configuration and command history with completion",
    "Copy terminal, Export to TXT, and Clear actions",
    "Live status: online/offline, RX/TX counters, port @ baud",
]

TECH_STACK = "Python 3.10+   -   PySide6 (Qt 6)   -   pyserial"
CREDITS = (
    "UI font: Nunito Sans (SIL Open Font License).   "
    "Icons: Lucide via Iconify (ISC / MIT).   "
    "License: MIT."
)


def _section_label(text: str) -> QLabel:
    """A small, muted heading placed between the About sections."""
    lbl = QLabel(text.upper())
    lbl.setStyleSheet(
        "color: %s; background: transparent; font-size: 10px; "
        "font-weight: 700;" % PALETTE["text_muted"])
    return lbl


class AboutDialog(QDialog):
    """A frameless, rounded neumorphic "About" card.

    The rounded card is painted manually (translucent window + ``paintEvent``)
    because a top-level widget cannot get rounded corners from a style sheet
    alone.  Dragging reuses the same ``startSystemMove`` trick as the main
    title bar, so the dialog can be repositioned like a native window.
    """

    CARD_RADIUS = 16
    SHADOW_PAD = 18          # transparent margin so the card can "breathe"
    WIDTH = 470

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("aboutDialog")
        self.setWindowTitle("About %s" % APP_NAME)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setModal(True)
        self.setFixedWidth(self.WIDTH)
        self._build_ui()

    # ------------------------------------------------------------------ ui #
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(self.SHADOW_PAD, self.SHADOW_PAD,
                                self.SHADOW_PAD, self.SHADOW_PAD)
        root.setSpacing(0)

        body = QVBoxLayout()
        body.setContentsMargins(26, 22, 26, 20)
        body.setSpacing(12)

        body.addLayout(self._build_header())
        body.addWidget(self._divider())
        body.addWidget(self._wrap(APP_DESCRIPTION))
        body.addWidget(_section_label("Features"))
        body.addWidget(self._bullet_list(FEATURES))
        body.addWidget(_section_label("Built with"))
        body.addWidget(self._wrap(TECH_STACK))
        body.addWidget(self._divider())
        body.addWidget(_section_label("Links"))
        body.addWidget(self._links())
        body.addWidget(self._muted(CREDITS))
        body.addLayout(self._build_footer())

        root.addLayout(body)

    def _build_header(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(16)

        icon = QLabel()
        icon.setFixedSize(56, 56)
        icon.setStyleSheet("background: transparent;")
        pix = QPixmap(str(APP_ICON_PATH))
        if not pix.isNull():
            icon.setPixmap(pix.scaled(56, 56, Qt.KeepAspectRatio,
                                      Qt.SmoothTransformation))
        row.addWidget(icon, 0, Qt.AlignTop)

        text = QVBoxLayout()
        text.setSpacing(3)

        name = QLabel(APP_NAME)
        name.setStyleSheet(
            "color: %s; background: transparent; font-size: 20px; "
            "font-weight: 700;" % PALETTE["text"])
        text.addWidget(name)

        version = QLabel("Version %s" % APP_VERSION)
        version.setStyleSheet(
            "color: %s; background: transparent; font-size: 11px; "
            "font-weight: 600;" % PALETTE["accent"])
        text.addWidget(version)

        tagline = QLabel(APP_TAGLINE)
        tagline.setWordWrap(True)
        tagline.setStyleSheet(
            "color: %s; background: transparent; font-size: 11px;"
            % PALETTE["text_muted"])
        text.addWidget(tagline)

        row.addLayout(text, 1)
        return row

    def _divider(self) -> QFrame:
        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet("background: %s; border: none;" % PALETTE["deep"])
        return line

    def _wrap(self, text: str, color: str | None = None) -> QLabel:
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(
            "color: %s; background: transparent; font-size: 11px;"
            % (color or PALETTE["text"]))
        return lbl

    def _muted(self, text: str) -> QLabel:
        return self._wrap(text, PALETTE["text_muted"])


    def _bullet_list(self, items: list[str]) -> QWidget:
        box = QWidget()
        box.setStyleSheet("background: transparent;")
        col = QVBoxLayout(box)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(5)

        for item in items:
            row = QHBoxLayout()
            row.setSpacing(8)

            dot = QLabel("\u2022")
            dot.setFixedWidth(10)
            dot.setStyleSheet(
                "color: %s; background: transparent; font-size: 12px;"
                % PALETTE["accent"])

            txt = QLabel(item)
            txt.setWordWrap(True)
            txt.setStyleSheet(
                "color: %s; background: transparent; font-size: 11px;"
                % PALETTE["text"])

            row.addWidget(dot, 0, Qt.AlignTop)
            row.addWidget(txt, 1)
            col.addLayout(row)

        return box

    def _links(self) -> QLabel:
        accent = PALETTE["accent"]
        repo_text = APP_REPO.replace("https://", "")
        author_url = "https://github.com/%s" % APP_AUTHOR
        html = (
            'Repository: <a style="color:%(a)s;" href="%(r)s">%(rt)s</a>'
            '&nbsp;&nbsp;&nbsp;'
            'Author: <a style="color:%(a)s;" href="%(au)s">%(an)s</a>'
            % {"a": accent, "r": APP_REPO, "rt": repo_text,
               "au": author_url, "an": APP_AUTHOR}
        )
        lbl = QLabel(html)
        lbl.setTextFormat(Qt.RichText)
        lbl.setOpenExternalLinks(True)
        lbl.setStyleSheet("background: transparent; font-size: 11px;")
        return lbl

    def _build_footer(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.addStretch(1)
        btn_close = NeumorphicButton("Close", accent=True)
        btn_close.setToolTip("Close the About panel (Esc)")
        # Follow the exact same metrics as every other button in the app (width
        # comes from sizeHint) and pin the height so a short dialog can never
        # squash the footer out of proportion.
        btn_close.setMinimumWidth(BUTTON_MIN_W)
        btn_close.setFixedHeight(CONTROL_H)
        btn_close.clicked.connect(self.accept)
        row.addWidget(btn_close)
        return row

    # -------------------------------------------------------------- chrome #
    def paintEvent(self, event) -> None:   # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        pad = self.SHADOW_PAD - 2
        rect = QRectF(self.rect()).adjusted(pad, pad, -pad, -pad)
        r = float(self.CARD_RADIUS)

        p.setPen(Qt.NoPen)
        p.setBrush(QColor(PALETTE["bg"]))
        p.drawRoundedRect(rect, r, r)

        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(PALETTE["deep"]), 1.2))
        p.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), r, r)

    def mousePressEvent(self, event) -> None:   # noqa: N802
        if event.button() == Qt.LeftButton:
            handle = self.windowHandle()
            if handle is not None:
                handle.startSystemMove()
        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:   # noqa: N802
        if event.key() == Qt.Key_Escape:
            self.reject()
            return
        super().keyPressEvent(event)
