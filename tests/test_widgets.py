import unittest

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor, QIcon
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLineEdit, QVBoxLayout, QWidget

from icons import icon
from widgets import TerminalInput, TerminalView


class WidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(
            ["serial-monitor-tests", "-platform", "offscreen"])

    def setUp(self):
        self.window = QWidget()
        layout = QVBoxLayout(self.window)
        self.input = TerminalInput()
        self.other = QLineEdit()
        self.terminal = TerminalView()
        layout.addWidget(self.input)
        layout.addWidget(self.other)
        layout.addWidget(self.terminal)
        self.window.resize(600, 300)
        self.window.show()
        self.window.activateWindow()
        self.input.setFocus()
        self.app.processEvents()

    def tearDown(self):
        self.input._completer.popup().hide()
        self.window.close()
        self.app.processEvents()

    def test_history_navigation_restores_unsent_draft(self):
        self.input.remember("first")
        self.input.remember("second")
        self.input.setText("unsent draft")
        for key, expected in (
            (Qt.Key_Up, "second"), (Qt.Key_Up, "first"), (Qt.Key_Up, "first"),
            (Qt.Key_Down, "second"), (Qt.Key_Down, "unsent draft"),
            (Qt.Key_Down, "unsent draft"),
        ):
            QTest.keyClick(self.input, key)
            self.assertEqual(self.input.text(), expected)

    def test_editing_a_recalled_command_preserves_the_edit_as_draft(self):
        self.input.remember("first")
        QTest.keyClick(self.input, Qt.Key_Up)
        QTest.keyClicks(self.input, " edited")
        QTest.keyClick(self.input, Qt.Key_Up)
        self.assertEqual(self.input.text(), "first")
        QTest.keyClick(self.input, Qt.Key_Down)
        self.assertEqual(self.input.text(), "first edited")

    def test_history_is_bounded_and_skips_consecutive_duplicates(self):
        for index in range(self.input.MAX_HISTORY + 10):
            self.input.remember("command %d" % index)
        last = self.input.history[-1]
        self.input.remember(last)

        self.assertEqual(len(self.input.history), self.input.MAX_HISTORY)
        self.assertEqual(self.input.history[0], "command 10")
        self.assertEqual(self.input.history[-1], last)

    def test_invalid_saved_history_is_ignored(self):
        self.input.set_history([12, "", "valid", "valid", "two\nlines", "x" * 4097])
        self.assertEqual(self.input.history, ["valid"])
        self.input.set_history("not a list")
        self.assertEqual(self.input.history, [])

    def test_tab_completes_a_previous_command_without_sending(self):
        self.input.set_history(["status verbose"])
        sent = []
        self.input.returnPressed.connect(lambda: sent.append(self.input.text()))
        QTest.keyClicks(self.input, "stat")

        QTest.keyClick(self.input, Qt.Key_Tab)

        self.assertEqual(self.input.text(), "status verbose")
        self.assertEqual(sent, [])

    def test_tab_completes_a_token_from_received_text(self):
        self.input.add_reference("temperature=23 READY")
        self.input.setText("get RE")

        QTest.keyClick(self.input, Qt.Key_Tab)

        self.assertEqual(self.input.text(), "get READY")

    def test_enter_sends_exact_typed_text_not_a_suggested_command(self):
        self.input.set_history(["status verbose"])
        sent = []
        self.input.returnPressed.connect(lambda: sent.append(self.input.text()))
        QTest.keyClicks(self.input, "stat")

        QTest.keyClick(self.input, Qt.Key_Return)

        self.assertEqual(sent, ["stat"])
        self.assertFalse(self.input._completer.popup().isVisible())

    def test_arrows_use_history_even_with_suggestions_open(self):
        self.input.set_history(["start", "stop"])
        QTest.keyClicks(self.input, "s")

        QTest.keyClick(self.input, Qt.Key_Up)

        self.assertEqual(self.input.text(), "stop")
        QTest.keyClick(self.input, Qt.Key_Down)
        self.assertEqual(self.input.text(), "s")

    def test_explicit_suggestions_and_escape(self):
        self.input.set_history(["status"])
        QTest.keyClick(self.input, Qt.Key_Space, Qt.ControlModifier)
        self.assertTrue(self.input._completer.popup().isVisible())
        QTest.keyClick(self.input, Qt.Key_Escape)
        self.assertFalse(self.input._completer.popup().isVisible())
        self.assertEqual(self.input.text(), "")

    def test_tab_without_a_match_moves_keyboard_focus(self):
        QTest.keyClick(self.input, Qt.Key_Tab)
        self.assertTrue(self.other.hasFocus())

    def test_tab_does_not_apply_a_stale_completion_after_caret_moves(self):
        self.input.set_history(["status verbose"])
        QTest.keyClicks(self.input, "stat")
        QTest.keyClick(self.input, Qt.Key_Left)
        self.assertEqual(self.input.cursorPosition(), 3)

        QTest.keyClick(self.input, Qt.Key_Tab)

        self.assertEqual(self.input.text(), "stat")
        self.assertTrue(self.other.hasFocus())

    def test_ctrl_c_retains_native_input_selection_copy(self):
        self.input.setText("selected command")
        self.input.selectAll()

        QTest.keyClick(self.input, Qt.Key_C, Qt.ControlModifier)

        self.assertEqual(self.app.clipboard().text(), "selected command")

    def test_reference_memory_is_bounded(self):
        for index in range(500):
            self.input.add_reference("value%d" % index)
        self.assertEqual(len(self.input._references), self.input.MAX_REFERENCES)
        self.assertIn("value499", self.input._references)

    def test_appending_output_keeps_follow_enabled(self):
        self.terminal.append_text("line\n" * 100)
        self.terminal.append_text("another\n")

        self.assertTrue(self.terminal._follow)
        bar = self.terminal.verticalScrollBar()
        self.assertEqual(bar.value(), bar.maximum())

    def test_user_scroll_pauses_follow_and_append_preserves_position(self):
        self.terminal.append_text("line\n" * 100)
        bar = self.terminal.verticalScrollBar()
        bar.setValue(10)
        self.assertFalse(self.terminal._follow)

        self.terminal.append_text("new output\n")

        self.assertEqual(bar.value(), 10)
        self.assertFalse(self.terminal._follow)
        self.terminal.set_follow(True)
        self.assertEqual(bar.value(), bar.maximum())

    def test_appending_does_not_replace_terminal_selection(self):
        self.terminal.append_text("selected output\n")
        cursor = self.terminal.textCursor()
        cursor.setPosition(0)
        cursor.setPosition(8, QTextCursor.KeepAnchor)
        self.terminal.setTextCursor(cursor)

        self.terminal.append_text("new output\n")

        self.assertEqual(self.terminal.textCursor().selectedText(), "selected")

    def test_bundled_icon_has_normal_active_and_disabled_pixmaps(self):
        glyph = icon("plug")
        self.assertFalse(glyph.isNull())
        self.assertFalse(glyph.pixmap(24, 24, QIcon.Normal, QIcon.Off).isNull())
        self.assertFalse(glyph.pixmap(24, 24, QIcon.Normal, QIcon.On).isNull())
        self.assertFalse(glyph.pixmap(24, 24, QIcon.Disabled, QIcon.Off).isNull())


if __name__ == "__main__":
    unittest.main()
