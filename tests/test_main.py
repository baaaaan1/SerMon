import tempfile
import unittest
from pathlib import Path
from time import monotonic
from unittest.mock import PropertyMock, patch

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QLabel

from main import MainWindow
from frameless import FramelessTitleBar
from theme import PALETTE, build_qss
from widgets import NeumorphicButton
from serial_engine import PortInfo
from test_serial_engine import FakeSerial, SerialFactory, SignalLog


class MainWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(
            ["serial-monitor-tests", "-platform", "offscreen"])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.settings = QSettings(
            str(Path(self.directory.name) / "settings.ini"), QSettings.IniFormat)
        self.ports = patch("main.available_ports", return_value=[
            PortInfo("COM2", "Standard port"), PortInfo("COM3", "USB serial")])
        self.ports.start()
        self.windows = []

    def tearDown(self):
        for window in self.windows:
            window.close()
        self.app.processEvents()
        self.ports.stop()
        self.directory.cleanup()

    def window(self):
        window = MainWindow(settings=self.settings)
        self.windows.append(window)
        return window

    def test_preferences_round_trip_without_connecting_on_launch(self):
        window = self.window()
        window.combo_port.setCurrentIndex(window.combo_port.findData("COM2"))
        window.combo_baud.setCurrentText("9600")
        window.combo_line_ending.setCurrentIndex(
            window.combo_line_ending.findData("lf"))
        window.act_dtr.setChecked(False)
        window.act_auto_reconnect.setChecked(True)
        window.act_auto_clear.setChecked(True)
        window.act_timestamp.setChecked(True)
        window.act_autoscroll.setChecked(False)
        window.tx_input.remember("saved command")
        self.assertTrue(window._settings_timer.isActive())
        window.close()

        restored = self.window()

        self.assertEqual(restored._selected_port(), "COM2")
        self.assertEqual(restored.combo_baud.currentText(), "9600")
        self.assertEqual(restored._rx_parser.mode.key, "lf")
        self.assertFalse(restored.mgr.dtr)
        self.assertTrue(restored.mgr.auto_reconnect)
        self.assertTrue(restored.btn_reconnect.isChecked())
        self.assertTrue(restored._auto_clear)
        self.assertTrue(restored.btn_auto_clear.isChecked())
        self.assertTrue(restored.act_timestamp.isChecked())
        self.assertFalse(restored.act_autoscroll.isChecked())
        self.assertFalse(restored.mgr.connection_requested)
        self.assertEqual(restored.tx_input.history, ["saved command"])

    def test_shortcut_dialog_and_title_bars_match_main_page_background(self):
        stylesheet = self.app.styleSheet()
        self.app.setStyleSheet(build_qss())
        window = self.window()

        def inspect(dialog):
            dialog.show()
            self.app.processEvents()
            titlebar = dialog.findChild(FramelessTitleBar)
            content = dialog.findChild(QLabel, "shortcutList")
            expected = QColor(PALETTE["bg"])
            self.assertTrue(dialog.windowFlags() & Qt.FramelessWindowHint)
            self.assertTrue(dialog.isModal())
            self.assertEqual(dialog.windowTitle(), "Keyboard Shortcuts")
            self.assertEqual(dialog.grab().toImage().pixelColor(2, 2), expected)
            self.assertEqual(titlebar.grab().toImage().pixelColor(2, 2), expected)
            self.assertEqual(window.titlebar.grab().toImage().pixelColor(2, 2), expected)
            self.assertIn("Ctrl+L: Clear Terminal", content.text())
            self.assertIn("Ctrl+Shift+C: Copy Terminal", content.text())
            self.assertFalse(titlebar.btn_min.isVisible())
            self.assertFalse(titlebar.btn_max.isVisible())
            close = next(button for button in dialog.findChildren(NeumorphicButton)
                         if button.text() == "Close")
            close.click()
            self.assertEqual(dialog.result(), QDialog.Accepted)

        try:
            with patch("main.QDialog.exec", inspect):
                window._show_shortcuts()
        finally:
            self.app.setStyleSheet(stylesheet)

    def test_shortcut_dialog_closes_with_escape(self):
        window = self.window()

        def inspect(dialog):
            dialog.show()
            self.app.processEvents()
            QTest.keyClick(dialog, Qt.Key_Escape)
            self.assertFalse(dialog.isVisible())
            self.assertEqual(dialog.result(), QDialog.Rejected)

        with patch("main.QDialog.exec", inspect):
            window._show_shortcuts()

    def test_missing_saved_port_is_not_replaced_by_another_device(self):
        self.settings.setValue("connection/port", "COM99")

        window = self.window()
        window.refresh_ports()

        self.assertEqual(window._selected_port(), "COM99")
        self.assertIn("unavailable", window.combo_port.currentText())

    def test_first_launch_prefers_usb_port(self):
        self.assertEqual(self.window()._selected_port(), "COM3")

    def test_invalid_saved_values_use_safe_defaults(self):
        self.settings.setValue("connection/baud", "invalid")
        self.settings.setValue("connection/dtr", "invalid")
        self.settings.setValue("terminal/line_ending", "invalid")
        self.settings.setValue("terminal/timestamps", ["invalid"])
        self.settings.setValue("window/geometry", "invalid")

        window = self.window()

        self.assertEqual(window.combo_baud.currentText(), "115200")
        self.assertTrue(window.mgr.dtr)
        self.assertEqual(window._rx_parser.mode.key, "crlf")
        self.assertFalse(window.act_timestamp.isChecked())

    def test_auto_clear_runs_before_connected_message_with_reconnect_enabled(self):
        window = self.window()
        window.act_auto_reconnect.setChecked(True)
        window.act_auto_clear.setChecked(True)
        window.terminal.append_text("old output\n")
        window._rx_parser.feed(b"old partial")
        window._rx_record_open = True

        window._on_connected("COM3")

        self.assertEqual(window.terminal.toPlainText(), "[Connected COM3 @ 115200]\n")
        self.assertEqual(window._rx_parser.flush(), "")
        self.assertFalse(window._rx_record_open)
        window._on_data(b"new\r\n")
        self.assertIn("new\n", window.terminal.toPlainText())
        window._on_connected("COM3")
        self.assertNotIn("new", window.terminal.toPlainText())

    def test_threaded_auto_reconnect_also_clears_old_output(self):
        window = self.window()
        factory = SerialFactory()
        first = FakeSerial(data=b"old record\r\n")
        factory.queue(first, FakeSerial(data=b"fresh record\r\n"))
        window.mgr._reconnect_delay = 0.02
        window.act_auto_reconnect.setChecked(True)
        window.act_auto_clear.setChecked(True)

        def wait_for_text(text):
            deadline = monotonic() + 2
            while text not in window.terminal.toPlainText() and monotonic() < deadline:
                QTest.qWait(10)
            self.assertIn(text, window.terminal.toPlainText())

        with patch("serial_engine.serial.Serial", factory):
            try:
                window.toggle_connect()
                wait_for_text("old record")
                first.lose_link()
                wait_for_text("fresh record")

                self.assertNotIn("old record", window.terminal.toPlainText())
                self.assertIn("[Connected COM3 @ 115200]", window.terminal.toPlainText())
                self.assertTrue(window.mgr.is_open)
                self.assertTrue(window.btn_auto_clear.isChecked())
                self.assertTrue(window.btn_reconnect.isChecked())
                self.assertEqual(factory.unexpected_calls, 0)
            finally:
                window.mgr.stop()

    def test_cancellation_rejects_already_queued_connection_and_data_events(self):
        window = self.window()
        factory = SerialFactory()
        factory.queue(FakeSerial(data=b"STALE\r\n"))
        log = SignalLog(window.mgr)
        window.act_auto_reconnect.setChecked(True)
        window.act_auto_clear.setChecked(True)
        window.terminal.append_text("important capture\n")

        with patch("serial_engine.serial.Serial", factory):
            try:
                window.toggle_connect()
                self.assertTrue(log.wait("data_received", b"STALE\r\n"))
                window.toggle_connect()
                self.app.processEvents()

                text = window.terminal.toPlainText()
                self.assertIn("important capture", text)
                self.assertNotIn("STALE", text)
                self.assertNotIn("[Connected", text)
                self.assertFalse(window.mgr.connection_requested)
            finally:
                window.mgr.stop()

    def test_natural_link_loss_keeps_previously_queued_rx_events(self):
        window = self.window()
        factory = SerialFactory()
        first = FakeSerial(data=b"last record\r\n")
        factory.queue(first)
        log = SignalLog(window.mgr)

        with patch("serial_engine.serial.Serial", factory):
            try:
                window.toggle_connect()
                self.assertTrue(log.wait("data_received", b"last record\r\n"))
                request_id = window.mgr.request_id
                first.lose_link()
                self.assertTrue(log.wait("disconnected", "unplugged"))
                self.app.processEvents()

                self.assertEqual(window.mgr.request_id, request_id)
                self.assertIn("last record", window.terminal.toPlainText())
                self.assertIn("Disconnected (unplugged)", window.terminal.toPlainText())
            finally:
                window.mgr.stop()

    def test_tx_failure_cannot_overtake_queued_partial_rx(self):
        window = self.window()
        factory = SerialFactory()
        first = FakeSerial(
            data=b"final partial", block_read=True, write_error=OSError("TX link lost"))
        factory.queue(first)
        log = SignalLog(window.mgr)

        with patch("serial_engine.serial.Serial", factory):
            try:
                window.toggle_connect()
                self.assertTrue(log.wait("connected", "COM3"))
                self.app.processEvents()
                first.allow_read.set()
                self.assertTrue(log.wait("data_received", b"final partial"))
                window.tx_input.setText("trigger failure")
                window.send()
                self.app.processEvents()

                self.assertIn("final partial", window.terminal.toPlainText())
                self.assertEqual(window._rx_parser.flush(), "")
                self.assertFalse(window.mgr.is_open)
            finally:
                first.release()
                window.mgr.stop()

    def test_retry_can_be_cancelled_while_port_is_closed(self):
        window = self.window()
        with patch.object(type(window.mgr), "connection_requested",
                          new_callable=PropertyMock, return_value=True):
            window._update_status()
            self.assertEqual(window.btn_connect.text(), "Cancel Retry")
            self.assertFalse(window.combo_port.isEnabled())
            with patch.object(window.mgr, "disconnect") as disconnect:
                window.toggle_connect()
            disconnect.assert_called_once_with()

    def test_toggle_is_connected_only_once(self):
        window = self.window()
        with patch.object(window.mgr, "set_auto_reconnect") as setter:
            window.act_auto_reconnect.setChecked(True)
        setter.assert_called_once_with(True)
        self.assertTrue(window.btn_reconnect.isChecked())

    def test_enabling_retries_uses_current_offline_port_and_baud(self):
        window = self.window()
        window.mgr.configure("COM99", 115200)
        window.combo_port.setCurrentIndex(window.combo_port.findData("COM2"))
        window.combo_baud.setCurrentText("9600")

        window.act_auto_reconnect.setChecked(True)

        self.assertEqual((window.mgr.port, window.mgr.baudrate), ("COM2", 9600))
        self.assertFalse(window.mgr.connection_requested)

    def test_export_uses_explicit_lf_newlines(self):
        window = self.window()
        window.terminal.clear_terminal()
        window.terminal.append_text("one\ntwo\n")
        path = Path(self.directory.name) / "output.txt"

        with patch("main.QFileDialog.getSaveFileName", return_value=(str(path), "")):
            window.export_txt()

        self.assertEqual(path.read_bytes(), b"one\ntwo\n")

    def test_send_appends_exact_selected_wire_suffix(self):
        window = self.window()
        for mode, suffix in (("none", b""), ("lf", b"\n"),
                             ("cr", b"\r"), ("crlf", b"\r\n")):
            with self.subTest(mode=mode):
                window.combo_line_ending.setCurrentIndex(
                    window.combo_line_ending.findData(mode))
                window.tx_input.setText("hello")
                expected = b"hello" + suffix
                with patch.object(window.mgr, "write", return_value=len(expected)) as write:
                    window.send()
                write.assert_called_once_with(expected)
                self.assertEqual(window.tx_input.text(), "")

    def test_failed_or_partial_send_keeps_input(self):
        window = self.window()
        for written in (-1, 2):
            with self.subTest(written=written):
                window.tx_input.setText("keep me")
                with patch.object(window.mgr, "write", return_value=written):
                    window.send()
                self.assertEqual(window.tx_input.text(), "keep me")
                self.assertEqual(window.tx_input.history, [])

    def test_primary_shortcuts_clear_and_copy_with_input_focused(self):
        window = self.window()
        window.show()
        window.activateWindow()
        window.tx_input.setFocus()
        self.app.processEvents()
        window.terminal.append_text("copy this\n")
        expected = window.terminal.toPlainText()

        QTest.keyClick(window.tx_input, Qt.Key_C, Qt.ControlModifier | Qt.ShiftModifier)
        self.assertEqual(self.app.clipboard().text(), expected)
        QTest.keyClick(window.tx_input, Qt.Key_L, Qt.ControlModifier)
        self.assertEqual(window.terminal.toPlainText(), "[Terminal cleared]\n")

    def test_focus_and_toggle_shortcuts(self):
        window = self.window()
        window.show()
        window.activateWindow()
        window.terminal.setFocus()
        self.app.processEvents()

        QTest.keyClick(window.terminal, Qt.Key_K, Qt.ControlModifier)
        self.assertTrue(window.tx_input.hasFocus())
        QTest.keyClick(window.tx_input, Qt.Key_R, Qt.ControlModifier)
        self.assertTrue(window.btn_reconnect.isChecked())
        self.assertFalse(window.mgr.connection_requested)
        QTest.keyClick(window.tx_input, Qt.Key_T, Qt.ControlModifier)
        self.assertTrue(window.btn_timestamp.isChecked())
        QTest.keyClick(window.tx_input, Qt.Key_D, Qt.ControlModifier)
        self.assertFalse(window.mgr.dtr)

    def test_ctrl_enter_connects_instead_of_sending_input(self):
        window = self.window()
        window.show()
        window.activateWindow()
        window.tx_input.setFocus()
        window.tx_input.setText("do not send")
        self.app.processEvents()

        with patch.object(window.mgr, "connect") as connect, \
                patch.object(window.mgr, "write") as write:
            QTest.keyClick(window.tx_input, Qt.Key_Return, Qt.ControlModifier)

        connect.assert_called_once_with()
        write.assert_not_called()

    def test_shortcuts_work_while_completion_popup_is_open(self):
        window = self.window()
        window.show()
        window.activateWindow()
        window.tx_input.setFocus()
        window.tx_input.set_history(["status verbose"])
        self.app.processEvents()
        QTest.keyClicks(window.tx_input, "stat")
        self.assertTrue(window.tx_input._completer.popup().isVisible())
        expected = window.terminal.toPlainText()

        QTest.keyClick(window.tx_input, Qt.Key_C, Qt.ControlModifier | Qt.ShiftModifier)
        self.assertEqual(self.app.clipboard().text(), expected)
        QTest.keyClick(window.tx_input, Qt.Key_L, Qt.ControlModifier)
        self.assertEqual(window.terminal.toPlainText(), "[Terminal cleared]\n")
        with patch.object(window.mgr, "connect") as connect, \
                patch.object(window.mgr, "write") as write:
            QTest.keyClick(window.tx_input, Qt.Key_Return, Qt.ControlModifier)
        connect.assert_called_once_with()
        write.assert_not_called()

    def test_clear_history_removes_saved_commands_and_completion_memory(self):
        window = self.window()
        window.tx_input.remember("secret command")
        window.tx_input.setText("unsent draft")

        window.clear_command_history()

        self.assertEqual(window.tx_input.history, [])
        self.assertEqual(window.tx_input._references, {})
        self.assertEqual(window.tx_input.text(), "unsent draft")
        self.assertEqual(self.settings.value("terminal/history"), [])

    def test_scrolling_synchronizes_autoscroll_action_and_button(self):
        window = self.window()
        window.show()
        self.app.processEvents()
        window.terminal.append_text("line\n" * 100)

        window.terminal.verticalScrollBar().setValue(0)

        self.assertFalse(window.act_autoscroll.isChecked())
        self.assertFalse(window.btn_autoscroll.isChecked())
        window.btn_autoscroll.click()
        self.assertTrue(window.act_autoscroll.isChecked())
        self.assertTrue(window.terminal._follow)

    def test_partial_stream_and_system_status_are_separate_lines(self):
        window = self.window()
        window.terminal.clear_terminal()
        window.combo_line_ending.setCurrentIndex(
            window.combo_line_ending.findData("none"))
        window._on_data(b"partial")

        window._on_status("status")

        self.assertEqual(window.terminal.toPlainText(), "partial\n[status]\n")


if __name__ == "__main__":
    unittest.main()
