"""Terminal display widget backed by a Qt-free view-model.

The :class:`TerminalView` owns a read-only ``QTextEdit`` and renders the textual
output produced by a :class:`~app.models.terminal.TerminalViewModel`.  It handles
the viewport concerns (autoscroll on/off) while all rendering logic stays in the
view-model.
"""

from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QKeySequence,
    QShortcut,
    QTextCharFormat,
    QTextCursor,
)
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLineEdit,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from serial_engine.protocols import ParsedEvent

from ..models.terminal import TerminalViewModel
from ..theme import Theme, get_theme_manager


class TerminalView(QWidget):
    """Render a :class:`TerminalViewModel` into a read-only ``QTextEdit``.

    In addition to drawing incoming lines it owns the *viewport* features of the
    terminal: RX/TX colouring, autoscroll, word wrap, a scrollback limit, pause /
    resume, a collapsible find bar and copy helpers.  Display state is always read
    from the shared :class:`~app.models.terminal.TerminalOptions` so toggles in the
    window cascade here without extra plumbing.
    """

    def __init__(self, model: TerminalViewModel | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._model = model or TerminalViewModel()
        self._paused = False
        self._matches: list[QTextCursor] = []
        self._current_match = -1

        self._text = QTextEdit(self)
        self._text.setReadOnly(True)
        self._text.setPlaceholderText("Serial output appears here…")
        self._text.setAcceptRichText(False)
        self._apply_scrollback_limit()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_find_bar())
        layout.addWidget(self._text)

        self._apply_word_wrap()
        self._install_shortcuts()
        get_theme_manager().theme_changed.connect(self._recolor)

    @property
    def model(self) -> TerminalViewModel:
        """The backing view-model (shared with the window)."""
        return self._model

    @property
    def text(self) -> QTextEdit:
        """The underlying ``QTextEdit`` (exposed for tests and inspection)."""
        return self._text

    @property
    def paused(self) -> bool:
        """Whether incoming lines are currently being frozen on screen."""
        return self._paused

    def to_plain_text(self) -> str:
        """Return the currently visible terminal text."""
        return self._text.toPlainText()

    # -- Incoming / outgoing data -------------------------------------------

    def append_event(self, event: ParsedEvent) -> None:
        """Render *event* into the terminal, honouring the autoscroll option."""
        line = self._model.append_event(event)
        if not self._paused:
            self._append([line])

    def append_events(self, events: Iterable[ParsedEvent]) -> None:
        """Render a batch of *events* in a single pass (efficient for RX bursts).

        Lines received while paused are buffered in the view-model but not drawn,
        so pausing on a fast stream keeps the UI responsive and nothing is lost.
        """
        lines = self._model.append_events(events)
        if not self._paused:
            self._append(lines)

    def append_tx(self, text: str) -> None:
        """Render a transmitted *text* line into the terminal."""
        line = self._model.append_tx(text)
        if not self._paused:
            self._append([line])

    def on_connect(self) -> None:
        """Draw any connect marker(s) produced by the view-model."""
        if self._model.options.clear_on_connect:
            self._text.clear()
        marker = self._model.on_connect()
        if marker is not None:
            self._append([marker])

    def on_disconnect(self) -> None:
        """Draw the EOF marker produced by the view-model."""
        marker = self._model.on_disconnect()
        if marker is not None:
            self._append([marker])

    def clear(self) -> None:
        """Clear both the view-model buffer and the visible text."""
        self._model.clear()
        self._text.clear()
        self._clear_search()

    # -- Display toggles ----------------------------------------------------

    def set_paused(self, paused: bool) -> None:
        """Freeze (or resume) the on-screen output without stopping the serial RX.

        Lines received while paused are still accumulated in the view-model and are
        re-rendered in full when the terminal is resumed.
        """
        if self._paused == paused:
            return
        self._paused = paused
        if not paused:
            self._rewrite()

    def pause(self) -> None:
        """Freeze the on-screen output."""
        self.set_paused(True)

    def resume(self) -> None:
        """Unfreeze the output and render everything received while paused."""
        self.set_paused(False)

    def toggle_pause(self) -> None:
        """Toggle the paused state."""
        self.set_paused(not self._paused)

    def set_word_wrap(self, enabled: bool) -> None:
        """Enable/disable word wrap on the terminal content."""
        self._model.options.word_wrap = bool(enabled)
        self._apply_word_wrap()

    def set_scrollback_limit(self, limit: int) -> None:
        """Change the maximum number of buffered lines (``0`` = unlimited)."""
        self._model.set_max_lines(int(limit))
        self._apply_scrollback_limit()

    def copy_selection(self) -> None:
        """Copy the current selection to the system clipboard."""
        self._text.copy()

    def copy_all(self) -> None:
        """Copy the whole visible terminal text to the system clipboard."""
        QApplication.clipboard().setText(self._text.toPlainText())

    # -- Internal rendering --------------------------------------------------

    def _append(self, lines: Iterable[str]) -> None:
        """Draw already-rendered *lines* at the end of the document.

        Single-pass insertion keeps large RX bursts cheap; the scrollbar is then
        driven at the end so autoscroll-on follows the newest data while
        autoscroll-off keeps the viewport perfectly still.
        """
        lines = list(lines)
        if not lines:
            return
        self._insert_lines(lines)
        if self._model.options.autoscroll:
            self._scroll_to_end()

    def _insert_lines(self, lines: Iterable[str], theme: Theme | None = None) -> None:
        """Insert *lines* at the end of the document using one shared cursor."""
        theme = theme or get_theme_manager().theme
        cursor = self._text.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        for line in lines:
            self._insert_colored(cursor, line, theme)

    def _insert_colored(self, cursor: QTextCursor, line: str, theme: Theme) -> None:
        """Insert *line* at *cursor*, applying the per-line accent when present."""
        color = self._color_for(line, theme)
        if color is not None:
            fmt = QTextCharFormat()
            fmt.setForeground(QBrush(QColor(color)))
            cursor.setCharFormat(fmt)
            cursor.insertText(line)
            # Reset the char format so subsequent data lines use the default.
            cursor.setCharFormat(QTextCharFormat())
        else:
            cursor.insertText(line)

    def _rewrite(self, theme: Theme | None = None) -> None:
        """Replace the visible text with the current model buffer (preserving position)."""
        lines = self._model.lines
        scrollbar = self._text.verticalScrollBar()
        prev = scrollbar.value()
        self._text.clear()
        self._insert_lines(lines, theme)
        if self._model.options.autoscroll:
            self._scroll_to_end()
        else:
            scrollbar.setValue(prev)

    def _recolor(self, theme: Theme) -> None:
        """Re-render the visible terminal with *theme* so markers follow the theme."""
        self._rewrite(theme)

    def _scroll_to_end(self) -> None:
        """Jump the vertical scrollbar to its maximum value."""
        scrollbar = self._text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _apply_word_wrap(self) -> None:
        """Apply the current word-wrap option to the editor."""
        mode = (
            QTextEdit.LineWrapMode.WidgetWidth
            if self._model.options.word_wrap
            else QTextEdit.LineWrapMode.NoWrap
        )
        self._text.setLineWrapMode(mode)

    def _apply_scrollback_limit(self) -> None:
        """Apply the scrollback limit to the underlying document.

        A document always reserves one trailing (empty) block for the final
        newline, so the block-count limit is set one higher than the line limit
        to keep the *content* aligned with the view-model buffer.
        """
        limit = self._model.options.max_lines
        self._text.document().setMaximumBlockCount((limit + 1) if limit else 0)

    @staticmethod
    def _color_for(line: str, theme: Theme) -> str | None:
        """Return the accent colour for a system marker or RX/TX line, else ``None``."""
        if "--- Connected ---" in line:
            return theme.marker_connected
        if "--- Disconnected" in line:
            return theme.marker_eof
        if " RX  " in line or line.startswith("RX  "):
            return theme.rx
        if " TX  " in line or line.startswith("TX  "):
            return theme.tx
        return None

    # -- Find bar ------------------------------------------------------------

    def _build_find_bar(self) -> QWidget:
        """Create the collapsible search bar (hidden until toggled)."""
        self._find_bar = QWidget(self)
        self._find_bar.setObjectName("terminalFindBar")
        layout = QHBoxLayout(self._find_bar)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(4)

        self._search_input = QLineEdit(self._find_bar)
        self._search_input.setObjectName("terminalFindInput")
        self._search_input.setPlaceholderText("Find…")
        self._search_input.setClearButtonEnabled(True)
        layout.addWidget(self._search_input)

        prev_btn = QToolButton(self._find_bar)
        prev_btn.setText("▲")
        prev_btn.setToolTip("Previous match")
        prev_btn.clicked.connect(self._find_prev)
        layout.addWidget(prev_btn)

        next_btn = QToolButton(self._find_bar)
        next_btn.setText("▼")
        next_btn.setToolTip("Next match")
        next_btn.clicked.connect(self._find_next)
        layout.addWidget(next_btn)

        close_btn = QToolButton(self._find_bar)
        close_btn.setObjectName("terminalFindClose")
        close_btn.setText("✕")
        close_btn.setToolTip("Close find bar (Esc)")
        close_btn.clicked.connect(self.close_find)
        layout.addWidget(close_btn)

        layout.addStretch(1)

        self._search_input.textChanged.connect(self._update_search)
        self._search_input.returnPressed.connect(self._find_next_or_first)
        self._find_bar.hide()
        return self._find_bar

    def _install_shortcuts(self) -> None:
        """Bind the Esc key so it closes the find bar when the terminal is active."""
        esc = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        esc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        esc.activated.connect(self._on_escape)

    def _on_escape(self) -> None:
        """Close the find bar when it is visible; otherwise do nothing."""
        if not self._find_bar.isHidden():
            self.close_find()

    def toggle_find(self) -> None:
        """Show/hide the find bar."""
        if self._find_bar.isHidden():
            self._find_bar.show()
            self._search_input.setFocus()
            self._search_input.selectAll()
        else:
            self.close_find()

    def close_find(self) -> None:
        """Hide the find bar and clear any search highlighting."""
        self._find_bar.hide()
        self._clear_search()
        self._text.setFocus()

    def is_find_visible(self) -> bool:
        """Return whether the find bar is currently shown."""
        return not self._find_bar.isHidden()

    # -- Search implementation ----------------------------------------------

    def _update_search(self, text: str) -> None:
        """Recompute the match set from *text* and re-apply the highlights."""
        self._matches = self._find_matches(text)
        self._current_match = -1
        self._apply_highlights()

    def _find_matches(self, text: str) -> list[QTextCursor]:
        """Return a list of cursors for every occurrence of *text* in the document."""
        if not text:
            return []
        doc = self._text.document()
        matches: list[QTextCursor] = []
        position = 0
        while True:
            cursor = doc.find(text, position)
            if cursor.isNull():
                break
            matches.append(cursor)
            end = cursor.selectionEnd()
            if end >= doc.characterCount():
                break
            position = end
        return matches

    def _apply_highlights(self) -> None:
        """Colour every current match with the theme accent."""
        theme = get_theme_manager().theme
        selections: list[QTextEdit.ExtraSelection] = []
        for match in self._matches:
            selection = QTextEdit.ExtraSelection()
            fmt = QTextCharFormat()
            fmt.setBackground(QColor(theme.accent))
            fmt.setForeground(QColor(theme.selection_text))
            selection.format = fmt
            selection.cursor = match
            selections.append(selection)
        self._text.setExtraSelections(selections)

    def _clear_search(self) -> None:
        """Drop match state and remove all highlights."""
        self._matches = []
        self._current_match = -1
        self._text.setExtraSelections([])

    def _goto_match(self, index: int) -> None:
        """Move the cursor to the match at *index* (wrapping if needed)."""
        if not self._matches:
            return
        self._current_match = index % len(self._matches)
        self._text.setTextCursor(self._matches[self._current_match])
        self._text.ensureCursorVisible()

    def _find_next(self) -> None:
        """Jump to the next match."""
        self._goto_match(self._current_match + 1)

    def _find_prev(self) -> None:
        """Jump to the previous match."""
        self._goto_match(self._current_match - 1)

    def _find_next_or_first(self) -> None:
        """On Enter: go to the first match, or the next one if already navigating."""
        if not self._search_input.text():
            return
        if not self._matches:
            self._update_search(self._search_input.text())
        self._find_next()


