"""TX / command input widget with single-line and multiline modes.

The widget sits below the terminal and owns:

* a single-line :class:`QLineEdit` (the default) that sends on Enter, or a
  multiline :class:`QPlainTextEdit` that sends on Ctrl+Enter and inserts a
  newline on plain Enter;
* Send, Re-send and a multiline toggle button;
* a :class:`TxHistory` shared with the window for re-send and Up/Down
  navigation (Arrow Up/Down in single-line mode, Ctrl+Up/Down in multiline).

It emits :attr:`send_requested` with the text to transmit and
:attr:`resend_requested` with the last command when the Re-send button is used.
The window is responsible for encoding, line endings and writing to the port.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QToolButton,
    QWidget,
)

from ..models.tx_input import TxHistory

#: Glyph shown on the multiline toggle button.
_MULTILINE_GLYPH = "☰"


class TxInput(QWidget):
    """Single/multiline command input with history, send and re-send."""

    #: Emitted with the text to transmit (Send button / Enter / Ctrl+Enter).
    send_requested = Signal(str)
    #: Emitted with the last command when the Re-send button is activated.
    resend_requested = Signal(str)

    def __init__(
        self,
        history: TxHistory | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("txInput")
        self._history = history or TxHistory()
        self._multiline = False
        #: Guard so programmatic text changes do not reset history navigation.
        self._updating = False

        # -- Input widgets ----------------------------------------------------
        self._single = QLineEdit(self)
        self._single.setObjectName("txInputSingle")
        self._single.setPlaceholderText("Type a message to send… (Enter to send)")
        self._single.setClearButtonEnabled(True)

        self._multi = QPlainTextEdit(self)
        self._multi.setObjectName("txInputMultiline")
        self._multi.setPlaceholderText("Type a message to send… (Ctrl+Enter to send)")
        self._multi.setFixedHeight(96)
        self._multi.hide()  # Start in single-line mode.

        # -- Buttons ----------------------------------------------------------
        self._multiline_btn = QToolButton(self)
        self._multiline_btn.setObjectName("txMultilineBtn")
        self._multiline_btn.setText(_MULTILINE_GLYPH)
        self._multiline_btn.setCheckable(True)
        self._multiline_btn.setToolTip(
            "Toggle multiline input (Enter=newline, Ctrl+Enter=send)."
        )
        self._multiline_btn.setAutoRaise(True)

        self._send_btn = QPushButton("Send", self)
        self._send_btn.setObjectName("sendBtn")
        self._send_btn.setToolTip("Send the entered text (Enter / Ctrl+Enter).")

        self._resend_btn = QPushButton("Re-send", self)
        self._resend_btn.setObjectName("resendBtn")
        self._resend_btn.setToolTip("Send the previous command again.")
        self._resend_btn.setEnabled(False)

        self._clear_btn = QPushButton("Clear", self)
        self._clear_btn.setObjectName("clearBtn")
        self._clear_btn.setToolTip("Clear the terminal output.")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self._single, 1)
        layout.addWidget(self._multi, 1)
        layout.addWidget(self._multiline_btn)
        layout.addWidget(self._send_btn)
        layout.addWidget(self._resend_btn)
        layout.addWidget(self._clear_btn)

        # -- Wiring -----------------------------------------------------------
        self._single.returnPressed.connect(self._send)
        self._send_btn.clicked.connect(self._send)
        self._resend_btn.clicked.connect(self._on_resend)
        self._multiline_btn.clicked.connect(self._toggle_multiline)
        self._single.textChanged.connect(self._on_text_changed)
        self._multi.textChanged.connect(self._on_text_changed)
        self._single.installEventFilter(self)
        self._multi.installEventFilter(self)


    # -- Introspection --------------------------------------------------------

    @property
    def history(self) -> TxHistory:
        """The shared (Qt-free) transmit history."""
        return self._history

    @property
    def single_input(self) -> QLineEdit:
        """The single-line editor (always present, hidden in multiline mode)."""
        return self._single

    @property
    def multi_input(self) -> QPlainTextEdit:
        """The multiline editor (always present, hidden in single-line mode)."""
        return self._multi

    @property
    def input(self) -> QWidget:
        """The currently visible input widget."""
        return self._multi if self._multiline else self._single

    @property
    def send_btn(self) -> QPushButton:
        return self._send_btn

    @property
    def resend_btn(self) -> QPushButton:
        return self._resend_btn

    @property
    def clear_btn(self) -> QPushButton:
        return self._clear_btn

    @property
    def multiline_btn(self) -> QToolButton:
        return self._multiline_btn

    def is_multiline(self) -> bool:
        """Whether multiline input is currently active."""
        return self._multiline

    # -- Input helpers --------------------------------------------------------

    def text(self) -> str:
        """The current text of the visible input widget."""
        if self._multiline:
            return self._multi.toPlainText()
        return self._single.text()

    def clear_input(self) -> None:
        """Clear both editors and reset history navigation."""
        self._single.clear()
        self._multi.clear()
        self._history.reset()

    def set_selected(self, text: str) -> None:
        """Replace the visible editor's content with *text*."""
        self._set_text(text)

    def remember(self, command: str) -> None:
        """Record *command* in the history and refresh the re-send button."""
        self._history.add(command)
        self._refresh_resend()

    def set_send_enabled(self, enabled: bool) -> None:
        """Enable/disable sending (both editors and the Send button)."""
        self._single.setEnabled(enabled)
        self._multi.setEnabled(enabled)
        self._send_btn.setEnabled(enabled)
        self._refresh_resend()


    # -- Internal event handling ---------------------------------------------

    def eventFilter(self, watched: QObject, event) -> bool:
        """Intercept Up/Down for history and Ctrl+Enter to send in multiline."""
        if event.type() == QEvent.Type.KeyPress:
            key = event.key()
            ctrl = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
            if watched is self._single:
                if key in (Qt.Key.Key_Up, Qt.Key.Key_Down):
                    self._navigate(key == Qt.Key.Key_Up)
                    return True
            elif watched is self._multi:
                if (key in (Qt.Key.Key_Return, Qt.Key.Key_Enter)) and ctrl:
                    self._send()
                    return True
                if ctrl and key in (Qt.Key.Key_Up, Qt.Key.Key_Down):
                    self._navigate(key == Qt.Key.Key_Up)
                    return True
        return super().eventFilter(watched, event)

    def _send(self) -> None:
        """Emit the current text for sending (empty input is ignored)."""
        text = self.text()
        if text.strip():
            self.send_requested.emit(text)

    def _on_resend(self) -> None:
        """Re-send the most recent command, pre-filling the editor."""
        command = self._history.last()
        if command is None:
            return
        self.set_selected(command)
        self.resend_requested.emit(command)

    def _navigate(self, older: bool) -> None:
        """Move through history; Down past the newest clears the editor."""
        if older:
            command = self._history.previous()
            if command is not None:
                self._set_text(command)
        else:
            command = self._history.next()
            self._set_text("" if command is None else command)

    def _toggle_multiline(self) -> None:
        """Switch between single-line and multiline input."""
        self._multiline = self._multiline_btn.isChecked()
        self._single.setVisible(not self._multiline)
        self._multi.setVisible(self._multiline)
        self.input.setFocus()

    def _set_text(self, text: str) -> None:
        """Set the visible editor's text without resetting history navigation."""
        self._updating = True
        try:
            if self._multiline:
                self._multi.setPlainText(text)
            else:
                self._single.setText(text)
        finally:
            self._updating = False

    def _on_text_changed(self, _text: str = "") -> None:
        """User edits return to the live input (abandon history navigation)."""
        if not self._updating:
            self._history.reset()

    def _refresh_resend(self) -> None:
        """Enable the Re-send button when connected and a command exists."""
        self._resend_btn.setEnabled(self._send_btn.isEnabled() and bool(self._history))

