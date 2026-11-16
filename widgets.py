"""Reusable neumorphism widgets.

The soft "dual shadow" (light top-left + dark bottom-right) is painted directly
in ``paintEvent`` because Qt's QSS does not support ``box-shadow``.  Buttons are
rendered as soft, flat pills that sit *carved into* the surface (recessed), so
nothing pops out with a hard 3D shadow.
"""

from __future__ import annotations

import re

from PySide6.QtCore import Qt, QRectF, QSize, QDateTime, QEvent, Signal, QStringListModel
from PySide6.QtGui import (
    QColor, QPainter, QPainterPath, QPen, QBrush, QLinearGradient, QFont,
    QTextCursor, QTextCharFormat, QIcon,
)
from PySide6.QtWidgets import QAbstractButton, QFrame, QPlainTextEdit, QLineEdit, QCompleter

from theme import (
    PALETTE, UI_FONT, UI_FONT_SIZE, TERM_FONT, TERM_SIZE,
    CONTROL_H, BUTTON_PAD_H, BUTTON_MIN_W,
)


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
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCheckable(toggle)
        self.setMinimumHeight(CONTROL_H)
        self.setFont(QFont(UI_FONT, UI_FONT_SIZE))

    def sizeHint(self) -> QSize:
        fm = self.fontMetrics()
        if not self.icon().isNull() and not self.text():
            return QSize(CONTROL_H, CONTROL_H)
        w = fm.horizontalAdvance(self.text()) + 2 * BUTTON_PAD_H
        if not self.icon().isNull():
            w += 26
        return QSize(max(w, BUTTON_MIN_W), CONTROL_H)

    def minimumSizeHint(self) -> QSize:    # noqa: N802
        # Never let a layout squeeze a button below the shared control height,
        # otherwise it would stop matching the combos / line edits beside it.
        return self.sizeHint()

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
        if self.icon().isNull():
            p.drawText(rect, Qt.AlignCenter, self.text())
        else:
            text_width = self.fontMetrics().horizontalAdvance(self.text())
            content_width = 18 + (8 + text_width if self.text() else 0)
            left = rect.center().x() - content_width / 2
            icon_rect = QRectF(left, rect.center().y() - 9, 18, 18)
            mode = QIcon.Normal if self.isEnabled() else QIcon.Disabled
            state = QIcon.On if self._accent or self._active() else QIcon.Off
            self.icon().paint(p, icon_rect.toRect(), Qt.AlignCenter, mode, state)
            if self.text():
                text_rect = QRectF(left + 26, rect.top(), text_width, rect.height())
                p.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, self.text())
        if self.hasFocus():
            p.setPen(QPen(QColor(PALETTE["accent"]), 1, Qt.DotLine))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(rect.adjusted(2, 2, -2, -2), r - 2, r - 2)

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


class TerminalInput(QLineEdit):
    """Command entry with bounded history and completion from TX/RX memory."""

    history_changed = Signal()
    MAX_HISTORY = 200
    MAX_REFERENCES = 200
    MAX_ENTRY_LENGTH = 4096

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("terminalInput")
        self.setFont(QFont(TERM_FONT, TERM_SIZE))
        self.setMaxLength(self.MAX_ENTRY_LENGTH)
        self.setPlaceholderText("Type a command or data...")
        self.setAccessibleName("Serial command input")
        self.setToolTip(
            "Enter: send | Up/Down: command history | Tab: complete | "
            "Ctrl+Space: suggestions | Esc: dismiss suggestions\n"
            "Suggestions come from sent commands and received text.")
        self._history: list[str] = []
        self._history_index = 0
        self._draft = ""
        self._references: dict[str, None] = {}
        self._completion_start = 0
        self._model = QStringListModel(self)
        self._completer = QCompleter(self._model, self)
        self._completer.setCaseSensitivity(Qt.CaseInsensitive)
        self._completer.setMaxVisibleItems(6)
        self._completer.setWidget(self)
        self._completer.activated[str].connect(self._insert_completion)
        self._completer.popup().setToolTip(
            "Tab or click: complete | Enter: send typed text | Up/Down: history")
        self._completer.popup().installEventFilter(self)
        self.installEventFilter(self)
        self.textEdited.connect(self._edited)

    @property
    def history(self) -> list[str]:
        return list(self._history)

    def set_history(self, entries) -> None:
        self._history = []
        if isinstance(entries, (list, tuple)):
            for text in entries[-self.MAX_HISTORY:]:
                if (isinstance(text, str) and text.strip()
                        and len(text) <= self.MAX_ENTRY_LENGTH
                        and not any(c in text for c in "\r\n\x00")
                        and (not self._history or self._history[-1] != text)):
                    self._history.append(text)
        self._history_index = len(self._history)
        self._draft = ""

    def remember(self, text: str) -> None:
        """Record only a command that was successfully transmitted."""
        if text.strip() and (not self._history or self._history[-1] != text):
            self._history.append(text)
            self._history = self._history[-self.MAX_HISTORY:]
            self.history_changed.emit()
        self._history_index = len(self._history)
        self._draft = ""
        self.add_reference(text)
        self._completer.popup().hide()

    def clear_history(self) -> None:
        self.set_history([])
        self._references.clear()
        self._model.setStringList([])
        self._completer.popup().hide()
        self.history_changed.emit()

    def add_reference(self, text: str) -> None:
        for line in text.splitlines():
            line = line.strip()
            if not line or len(line) > self.MAX_ENTRY_LENGTH:
                continue
            for candidate in (line, *re.findall(r"[^\s\x00-\x1f\x7f]{2,}", line)):
                self._references.pop(candidate, None)
                self._references[candidate] = None
        while len(self._references) > self.MAX_REFERENCES:
            del self._references[next(iter(self._references))]

    def _edited(self, text: str) -> None:
        self._history_index = len(self._history)
        self._draft = text
        self._show_completions()

    def _navigate_history(self, step: int) -> None:
        self._completer.popup().hide()
        if not self._history:
            return
        if self._history_index == len(self._history):
            self._draft = self.text()
        self._history_index = max(0, min(len(self._history), self._history_index + step))
        text = (self._draft if self._history_index == len(self._history)
                else self._history[self._history_index])
        self.setText(text)
        self.setCursorPosition(len(text))

    def _show_completions(self, force: bool = False) -> bool:
        text = self.text()
        if self.cursorPosition() != len(text) or (not text and not force):
            self._model.setStringList([])
            self._completer.popup().hide()
            return False
        candidates = list(dict.fromkeys([
            *reversed(self._history), *reversed(self._references)]))
        prefix = text
        self._completion_start = 0
        matches = [c for c in candidates
                   if c.casefold().startswith(prefix.casefold()) and c != prefix]
        if not matches and text:
            self._completion_start = re.search(r"\S*$", text).start()
            prefix = text[self._completion_start:]
            if prefix:
                matches = [c for c in candidates if " " not in c
                           and c.casefold().startswith(prefix.casefold()) and c != prefix]
        self._model.setStringList(matches)
        self._completer.setCompletionPrefix(prefix)
        if not matches:
            self._completer.popup().hide()
            return False
        self._completer.setCurrentRow(0)
        rect = self.cursorRect()
        rect.setWidth(max(280, min(self.width(), 560)))
        self._completer.complete(rect)
        return True

    def _insert_completion(self, completion: str) -> None:
        self.setText(self.text()[:self._completion_start] + completion)
        self.setCursorPosition(len(self.text()))
        self._history_index = len(self._history)
        self._draft = self.text()
        self._completer.popup().hide()
        self.setFocus()

    def eventFilter(self, obj, event):
        if event.type() == QEvent.KeyPress:
            key = event.key()
            modifiers = event.modifiers()
            if modifiers == Qt.NoModifier:
                if key in (Qt.Key_Up, Qt.Key_Down):
                    self._navigate_history(-1 if key == Qt.Key_Up else 1)
                    return True
                if key == Qt.Key_Tab:
                    if self._show_completions(force=True):
                        self._insert_completion(self._completer.currentCompletion())
                        return True
                if key in (Qt.Key_Return, Qt.Key_Enter) and self._completer.popup().isVisible():
                    self._completer.popup().hide()
                    self.returnPressed.emit()
                    return True
                if key == Qt.Key_Escape and self._completer.popup().isVisible():
                    self._completer.popup().hide()
                    return True
            if key == Qt.Key_Space and modifiers == Qt.ControlModifier:
                self._show_completions(force=True)
                return True
        return super().eventFilter(obj, event)


class TerminalView(QPlainTextEdit):
    """Read-only terminal editor with auto-scroll and per-kind colouring."""

    follow_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("terminal")
        self.setReadOnly(True)
        self.setFrameStyle(QFrame.NoFrame)
        self.setFont(QFont(TERM_FONT, TERM_SIZE))
        self.setMaximumBlockCount(20000)
        self._follow = True
        self._timestamps = False
        self._at_line_start = True
        self._updating = False
        self._colors = {
            "rx":  QColor(PALETTE["terminal_rx"]),
            "tx":  QColor(PALETTE["terminal_tx"]),
            "sys": QColor(PALETTE["terminal_sys"]),
        }
        self.verticalScrollBar().valueChanged.connect(self._on_scroll)

    def set_follow(self, follow: bool) -> None:
        changed = self._follow != bool(follow)
        self._follow = bool(follow)
        if follow:
            self._scroll_bottom()
        if changed:
            self.follow_changed.emit(self._follow)

    def clear_terminal(self) -> None:
        self._updating = True
        self.clear()
        self._updating = False
        self._at_line_start = True

    def set_timestamps(self, enabled: bool) -> None:
        self._timestamps = bool(enabled)

    def finish_line(self, kind: str = "rx") -> None:
        """Add a line break only when displayed text has an open line."""
        if not self._at_line_start:
            self.append_text("\n", kind)

    def append_text(
        self,
        text: str,
        kind: str = "rx",
        timestamp_lines: bool = True,
        timestamp_start: bool = True,
    ) -> None:
        """Append coloured text.  ``kind`` is rx / tx / sys."""
        if not text:
            return
        scroll_position = self.verticalScrollBar().value()
        self._updating = True
        cursor = QTextCursor(self.document())
        cursor.movePosition(QTextCursor.End)
        fmt = QTextCharFormat()
        fmt.setForeground(self._colors.get(kind, self._colors["rx"]))
        if kind == "tx":
            fmt.setFontWeight(700)
        for index, part in enumerate(text.splitlines(keepends=True)):
            add_timestamp = timestamp_lines or index == 0
            if (self._timestamps and timestamp_start and add_timestamp
                    and self._at_line_start and kind in ("rx", "tx")):
                ts_fmt = QTextCharFormat()
                ts_fmt.setForeground(self._colors["sys"])
                ts = QDateTime.currentDateTime().toString("HH:mm:ss.zzz")
                cursor.insertText("[%s] " % ts, ts_fmt)
            cursor.insertText(part, fmt)
            self._at_line_start = part.endswith(("\r", "\n"))
        if self._follow:
            self._scroll_bottom()
        else:
            self.verticalScrollBar().setValue(scroll_position)
        self._updating = False

    def _scroll_bottom(self) -> None:
        bar = self.verticalScrollBar()
        updating = self._updating
        self._updating = True
        bar.setValue(bar.maximum())
        self._updating = updating

    def _on_scroll(self, value: int) -> None:
        bar = self.verticalScrollBar()
        # stop auto-following once the user scrolls away from the bottom
        if not self._updating:
            self.set_follow(value >= bar.maximum() - 1)

