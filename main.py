"""Serial Monitor - a neumorphism dark-mode serial port monitor.

Run from the project root::

    python main.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt, QEvent, QTimer, QSettings, QSignalBlocker, QByteArray
from PySide6.QtGui import QAction, QKeySequence, QFont, QCursor, QIcon
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QComboBox, QFileDialog, QMessageBox, QMenuBar, QSizePolicy, QGridLayout,
    QDialog, QScrollArea, QFrame,
)

from theme import PALETTE, build_qss, load_bundled_fonts, UI_FONT, UI_FONT_SIZE, UI_WEIGHT
from serial_engine import SerialManager, available_ports, PortInfo
from line_endings import DEFAULT_LINE_ENDING, LINE_ENDING_MODES, SerialTextParser
from widgets import NeumorphicButton, NeumorphicFrame, TerminalView, TerminalInput
from icons import icon
from frameless import FramelessTitleBar
from about import AboutDialog, APP_VERSION


BAUD_RATES = [300, 1200, 2400, 4800, 9600, 19200, 38400, 57600,
              115200, 230400, 460800, 921600]
APP_ICON_PATH = Path(__file__).resolve().parent / "assets" / "app_icon.ico"


class MainWindow(QMainWindow):
    def __init__(self, settings: QSettings | None = None):
        super().__init__()
        self.setWindowTitle("Serial Monitor")
        self.setWindowIcon(QIcon(str(APP_ICON_PATH)))
        # Frameless: the native caption is replaced by our themed title bar.
        self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_StyledBackground)
        self.resize(1000, 680)
        self.setMinimumSize(820, 600)

        self._settings = settings if settings is not None else QSettings(
            QSettings.IniFormat, QSettings.UserScope, "SerMon", "SerialMonitor")
        self._restoring_settings = True
        self._settings_error_reported = False
        self._preferred_port = ""
        self.mgr = SerialManager(self)
        self._rx_parser = SerialTextParser(DEFAULT_LINE_ENDING)
        self._rx_record_open = False
        self._auto_clear = False
        self._guard = False   # re-entrancy guard for toggle synchronisation

        self._build_menu()
        self._build_ui()
        self._wire()

        self._settings_timer = QTimer(self)
        self._settings_timer.setSingleShot(True)
        self._settings_timer.setInterval(250)
        self._settings_timer.timeout.connect(self._save_settings)
        self._load_settings()
        self.terminal.append_text("Serial Monitor ready.\n", "sys")
        self.refresh_ports()
        self._restoring_settings = False

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_status)
        self._timer.start(250)
        self._update_status()

        self._state_connected = False
        QApplication.instance().installEventFilter(self)

    # ------------------------------------------------------------------ menu #
    def _build_menu(self) -> None:
        bar = QMenuBar()
        self.menu_bar = bar
        bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        m_file = bar.addMenu("&File")
        act_export = QAction(icon("download"), "Export to TXT...", self)
        act_export.setShortcut(QKeySequence("Ctrl+E"))
        act_export.triggered.connect(self.export_txt)
        m_file.addAction(act_export)

        act_copy = QAction(icon("copy"), "Copy Terminal", self)
        act_copy.setShortcut(QKeySequence("Ctrl+Shift+C"))
        act_copy.triggered.connect(self.copy_terminal)
        m_file.addAction(act_copy)

        m_file.addSeparator()
        act_quit = QAction("Quit", self)
        act_quit.setShortcut(QKeySequence.Quit)
        act_quit.triggered.connect(self.close)
        m_file.addAction(act_quit)

        m_conn = bar.addMenu("&Connection")
        self.act_connect = QAction(icon("plug"), "Connect", self)
        self.act_connect.setShortcuts([
            QKeySequence("Ctrl+Return"), QKeySequence("Ctrl+Enter")])
        self.act_connect.triggered.connect(self.toggle_connect)
        m_conn.addAction(self.act_connect)

        self.act_dtr = QAction(icon("cable"), "DTR (Data Terminal Ready)", self)
        self.act_dtr.setCheckable(True)
        self.act_dtr.setChecked(True)
        self.act_dtr.setShortcut(QKeySequence("Ctrl+D"))
        self.act_dtr.toggled.connect(self._toggle_dtr)
        m_conn.addAction(self.act_dtr)

        m_conn.addSeparator()
        self.act_auto_reconnect = QAction(icon("refresh-cw"), "Auto Reconnect", self)
        self.act_auto_reconnect.setCheckable(True)
        self.act_auto_reconnect.setShortcut(QKeySequence("Ctrl+R"))
        self.act_auto_reconnect.toggled.connect(self._toggle_auto_reconnect)
        m_conn.addAction(self.act_auto_reconnect)

        self.act_auto_clear = QAction(icon("eraser"), "Auto Clear on Connection", self)
        self.act_auto_clear.setCheckable(True)
        self.act_auto_clear.setShortcut(QKeySequence("Ctrl+Shift+L"))
        self.act_auto_clear.toggled.connect(self._toggle_auto_clear)
        m_conn.addAction(self.act_auto_clear)

        m_view = bar.addMenu("&View")
        act_refresh = QAction(icon("refresh-cw"), "Refresh Ports", self)
        act_refresh.setShortcut(QKeySequence("F5"))
        act_refresh.triggered.connect(self.refresh_ports)
        m_view.addAction(act_refresh)

        self.act_autoscroll = QAction(icon("arrow-down-to-line"), "Auto Scroll", self)
        self.act_autoscroll.setCheckable(True)
        self.act_autoscroll.setChecked(True)
        self.act_autoscroll.setShortcut(QKeySequence("Ctrl+Shift+S"))
        self.act_autoscroll.toggled.connect(self._toggle_autoscroll)
        m_view.addAction(self.act_autoscroll)

        self.act_timestamp = QAction(icon("clock"), "Timestamps", self)
        self.act_timestamp.setCheckable(True)
        self.act_timestamp.setShortcut(QKeySequence("Ctrl+T"))
        self.act_timestamp.toggled.connect(self._toggle_timestamps)
        m_view.addAction(self.act_timestamp)

        act_clear = QAction(icon("trash"), "Clear Terminal", self)
        act_clear.setShortcut(QKeySequence("Ctrl+L"))
        act_clear.triggered.connect(self.clear_terminal)
        m_view.addAction(act_clear)

        act_history = QAction(icon("eraser"), "Clear Command History", self)
        act_history.setShortcut(QKeySequence("Ctrl+Shift+Delete"))
        act_history.triggered.connect(self.clear_command_history)
        m_view.addAction(act_history)

        act_focus = QAction(icon("terminal"), "Focus Command Input", self)
        act_focus.setShortcut(QKeySequence("Ctrl+K"))
        act_focus.triggered.connect(lambda: self.tx_input.setFocus())
        m_view.addAction(act_focus)

        m_help = bar.addMenu("&Help")
        act_shortcuts = QAction(icon("keyboard"), "Keyboard Shortcuts", self)
        act_shortcuts.setShortcut(QKeySequence("Ctrl+/"))
        act_shortcuts.triggered.connect(self._show_shortcuts)
        m_help.addAction(act_shortcuts)
        act_about = QAction("&About", self)
        act_about.setShortcut(QKeySequence("F1"))
        act_about.triggered.connect(self._about)
        m_help.addAction(act_about)

        self._shortcut_actions = []
        for menu in (m_file, m_conn, m_view, m_help):
            menu.setToolTipsVisible(True)
            for action in menu.actions():
                if not action.isSeparator():
                    self.addAction(action)
                    if action.shortcut():
                        self._shortcut_actions.append(action)
                        action.setToolTip("%s (%s)" % (
                            action.text().replace("&", ""),
                            action.shortcut().toString(QKeySequence.NativeText)))

    # ------------------------------------------------------------------- ui #
    def _label(self, text: str) -> QLabel:
        """A muted label used across the bars."""
        lbl = QLabel(text)
        lbl.setStyleSheet("color: %s; background: transparent;" % PALETTE["text_muted"])
        return lbl

    def _button(self, text: str, glyph: str, tooltip: str, **kwargs) -> NeumorphicButton:
        button = NeumorphicButton(text, **kwargs)
        button.setIcon(icon(glyph))
        button.setToolTip(tooltip)
        button.setAccessibleName(text or tooltip.split(" (")[0])
        return button

    def _build_ui(self) -> None:
        page = QWidget(self)
        page.setStyleSheet("background-color: %s;" % PALETTE["bg"])
        self.setCentralWidget(page)
        root = QVBoxLayout(page)
        root.setContentsMargins(12, 10, 12, 12)
        root.setSpacing(10)

        # ---------------- frameless title bar + menu ---------------- #
        self.titlebar = FramelessTitleBar(self, "Serial Monitor")
        root.addWidget(self.titlebar)
        root.addWidget(self.menu_bar)

        # ---------------- two-column configuration ---------------- #
        self.toolbar = NeumorphicFrame(radius=16)
        tb = QGridLayout(self.toolbar)
        tb.setContentsMargins(16, 12, 16, 12)
        tb.setHorizontalSpacing(24)
        tb.setVerticalSpacing(6)
        tb.setColumnStretch(0, 1)
        tb.setColumnStretch(1, 1)
        tb.addWidget(self._label("CONNECTION"), 0, 0)
        tb.addWidget(self._label("BEHAVIOR"), 0, 1)

        connection = QGridLayout()
        connection.setSpacing(8)
        connection.setColumnStretch(1, 1)
        self.combo_port = QComboBox()
        self.combo_port.setMinimumWidth(140)
        self.combo_port.setMinimumContentsLength(12)
        self.combo_port.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.combo_port.setToolTip("Serial port to open (Alt+P). Unavailable saved ports are retained.")
        self.combo_port.setAccessibleName("Serial port")
        port_label = self._label("&Port")
        port_label.setBuddy(self.combo_port)
        connection.addWidget(port_label, 0, 0)
        connection.addWidget(self.combo_port, 0, 1)
        self.btn_refresh = self._button("", "refresh-cw", "Refresh ports (F5)")
        connection.addWidget(self.btn_refresh, 0, 2, Qt.AlignRight)
        self.combo_baud = QComboBox()
        for b in BAUD_RATES:
            self.combo_baud.addItem(str(b))
        self.combo_baud.setCurrentText("115200")
        self.combo_baud.setMinimumWidth(110)
        self.combo_baud.setToolTip("Baud rate in bits per second (Alt+B). Applied on the next connection.")
        self.combo_baud.setAccessibleName("Baud rate")
        baud_label = self._label("&Baud")
        baud_label.setBuddy(self.combo_baud)
        connection.addWidget(baud_label, 1, 0)
        connection.addWidget(self.combo_baud, 1, 1)
        self.btn_connect = self._button(
            "Connect", "plug", "Connect / disconnect, or cancel retries (Ctrl+Enter)",
            accent=True, toggle=True)
        connection.addWidget(self.btn_connect, 1, 2)
        tb.addLayout(connection, 1, 0)

        behavior = QGridLayout()
        behavior.setSpacing(8)
        behavior.setColumnStretch(0, 1)
        behavior.setColumnStretch(1, 1)
        self.btn_dtr = self._button(
            "DTR", "cable", "Toggle Data Terminal Ready (Ctrl+D). May reset the connected board.",
            toggle=True)
        self.btn_dtr.setChecked(True)
        behavior.addWidget(self.btn_dtr, 0, 0)
        self.btn_reconnect = self._button(
            "Auto Reconnect", "refresh-cw",
            "Retry failed or lost connections every second (Ctrl+R). Disconnect cancels retries.",
            toggle=True)
        behavior.addWidget(self.btn_reconnect, 0, 1)
        self.btn_auto_clear = self._button(
            "Auto Clear", "eraser",
            "Clear output after every successful connection, including automatic reconnects (Ctrl+Shift+L).",
            toggle=True)
        behavior.addWidget(self.btn_auto_clear, 1, 0)
        self.btn_timestamp = self._button(
            "Timestamps", "clock", "Show timestamps on new RX / TX records (Ctrl+T)", toggle=True)
        behavior.addWidget(self.btn_timestamp, 1, 1)
        tb.addLayout(behavior, 1, 1)
        root.addWidget(self.toolbar)

        # ---------------- terminal tray ---------------- #
        self.term_frame = NeumorphicFrame(radius=16)
        tfl = QVBoxLayout(self.term_frame)
        tfl.setContentsMargins(10, 10, 10, 10)
        header = QHBoxLayout()
        header.addWidget(self._label("TERMINAL"))
        header.addStretch(1)
        self.btn_autoscroll = self._button(
            "Auto Scroll", "arrow-down-to-line",
            "Follow incoming output (Ctrl+Shift+S). Scrolling up pauses following.", toggle=True)
        self.btn_autoscroll.setChecked(True)
        header.addWidget(self.btn_autoscroll)
        tfl.addLayout(header)
        self.terminal = TerminalView()
        self.terminal.setToolTip(
            "RX: blue | TX: green | System: gray\n"
            "Ctrl+L: clear | Ctrl+Shift+C: copy all | Ctrl+C: copy selection")
        tfl.addWidget(self.terminal)
        root.addWidget(self.term_frame, 1)

        # ---------------- bottom bar tray ---------------- #
        self.bottom = NeumorphicFrame(radius=16)
        bl = QVBoxLayout(self.bottom)
        bl.setContentsMargins(14, 8, 14, 8)
        bl.setSpacing(8)

        row = QHBoxLayout()
        row.setSpacing(8)
        prompt = self._label(">")
        prompt.setStyleSheet("color: %s; font-size: 20px;" % PALETTE["accent"])
        row.addWidget(prompt)
        self.tx_input = TerminalInput()
        row.addWidget(self.tx_input, 1)
        self.btn_send = self._button("Send", "send", "Send command input (Enter)", accent=True)
        row.addWidget(self.btn_send)
        bl.addLayout(row)
        hint = self._label("Enter: send   |   Tab: complete   |   Up / Down: history   |   Ctrl+K: focus input")
        hint.setWordWrap(True)
        bl.addWidget(hint)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.combo_line_ending = QComboBox()
        for mode in LINE_ENDING_MODES:
            self.combo_line_ending.addItem(mode.label, mode.key)
        self.combo_line_ending.setCurrentIndex(
            self.combo_line_ending.findData(DEFAULT_LINE_ENDING))
        self.combo_line_ending.setMinimumWidth(150)
        self.combo_line_ending.setToolTip(
            "TX suffix and RX record delimiter (Alt+E). CRLF is carriage return followed by newline.\n"
            "No line ending sends no suffix and displays RX immediately.")
        self.combo_line_ending.setAccessibleName("Line ending")
        ending_label = self._label("Line &ending")
        ending_label.setBuddy(self.combo_line_ending)
        actions.addWidget(ending_label)
        actions.addWidget(self.combo_line_ending)
        actions.addStretch(1)
        self.btn_clear = self._button("Clear", "trash", "Clear terminal output, not command history (Ctrl+L)")
        actions.addWidget(self.btn_clear)
        self.btn_copy = self._button("Copy", "copy", "Copy all terminal output (Ctrl+Shift+C)")
        actions.addWidget(self.btn_copy)
        self.btn_export = self._button("Export", "download", "Export terminal as UTF-8 text (Ctrl+E)")
        actions.addWidget(self.btn_export)
        bl.addLayout(actions)

        srow = QHBoxLayout()
        srow.setSpacing(12)
        self.label_dot = QLabel()
        self.label_dot.setFixedSize(8, 8)
        self.label_status = QLabel("Offline")
        self.label_counters = QLabel("RX 0   TX 0")
        self.label_dtr = QLabel("DTR on")
        self.label_port = QLabel("")
        self.label_status.setToolTip("Serial connection state. Cancel Retry stops a pending connection.")
        self.label_counters.setToolTip("Received and transmitted bytes since the last successful connection")
        self.label_dtr.setToolTip("Current Data Terminal Ready state")
        self.label_port.setToolTip("Active port and baud rate, or the saved offline selection")
        muted = "color: %s; background: transparent; font-size: 13px;" % PALETTE["text_muted"]
        for w in (self.label_dot, self.label_status, self.label_counters,
                  self.label_dtr, self.label_port):
            w.setStyleSheet(muted)
        self.label_status.setStyleSheet(
            "color: %s; background: transparent; font-size: 13px; font-weight: 600;"
            % PALETTE["text_muted"])
        srow.addWidget(self.label_dot)
        srow.addWidget(self.label_status)
        srow.addWidget(self.label_counters)
        srow.addStretch(1)
        srow.addWidget(self.label_dtr)
        srow.addStretch(1)
        srow.addWidget(self.label_port)
        bl.addLayout(srow)
        root.addWidget(self.bottom)

    # ----------------------------------------------------------------- wire #
    def _wire(self) -> None:
        self._serial_handlers = {
            "data_received": self._on_data,
            "connected": self._on_connected,
            "disconnected": self._on_disconnected,
            "status_changed": self._on_status,
        }
        self.mgr.event_received.connect(
            self._on_serial_event, Qt.ConnectionType.QueuedConnection)

        self.btn_refresh.clicked.connect(self.refresh_ports)
        self.btn_connect.clicked.connect(self.toggle_connect)

        self.btn_dtr.toggled.connect(self._toggle_dtr)
        self.btn_reconnect.toggled.connect(self._toggle_auto_reconnect)
        self.btn_auto_clear.toggled.connect(self._toggle_auto_clear)
        self.btn_timestamp.toggled.connect(self._toggle_timestamps)
        self.btn_autoscroll.toggled.connect(self._toggle_autoscroll)
        self.terminal.follow_changed.connect(self._on_follow_changed)
        self.combo_line_ending.currentIndexChanged.connect(
            self._change_line_ending)
        self.combo_port.currentIndexChanged.connect(self._port_selection_changed)
        self.combo_baud.currentIndexChanged.connect(self._queue_save_settings)
        self.tx_input.history_changed.connect(self._queue_save_settings)

        self.btn_send.clicked.connect(self.send)
        self.tx_input.returnPressed.connect(self.send)
        self.btn_clear.clicked.connect(self.clear_terminal)
        self.btn_copy.clicked.connect(self.copy_terminal)
        self.btn_export.clicked.connect(self.export_txt)

    # ------------------------------------------------------------- toggles #
    def _sync_toggle(self, action, button, value) -> None:
        self._guard = True
        if action is not None:
            action.setChecked(bool(value))
        if button is not None:
            button.setChecked(bool(value))
        self._guard = False

    def _toggle_dtr(self, checked) -> None:
        if self._guard:
            return
        self.mgr.set_dtr(checked)
        self._sync_toggle(self.act_dtr, self.btn_dtr, checked)
        self._queue_save_settings()

    def _toggle_auto_reconnect(self, checked) -> None:
        if self._guard:
            return
        if checked and not self.mgr.connection_requested and self._selected_port():
            self.mgr.configure(self._selected_port(), int(self.combo_baud.currentText()))
        self.mgr.set_auto_reconnect(checked)
        self._sync_toggle(self.act_auto_reconnect, self.btn_reconnect, checked)
        self._queue_save_settings()
        self._update_status()

    def _toggle_auto_clear(self, checked) -> None:
        if self._guard:
            return
        self._auto_clear = bool(checked)
        self._sync_toggle(self.act_auto_clear, self.btn_auto_clear, checked)
        self._queue_save_settings()

    def _toggle_autoscroll(self, checked) -> None:
        if self._guard:
            return
        self.terminal.set_follow(checked)
        self._sync_toggle(self.act_autoscroll, self.btn_autoscroll, checked)
        self._queue_save_settings()

    def _on_follow_changed(self, checked: bool) -> None:
        self._sync_toggle(self.act_autoscroll, self.btn_autoscroll, checked)
        self._queue_save_settings()

    def _toggle_timestamps(self, checked) -> None:
        if self._guard:
            return
        self.terminal.set_timestamps(bool(checked))
        self._sync_toggle(self.act_timestamp, self.btn_timestamp, checked)
        self._queue_save_settings()

    def _change_line_ending(self, _index: int) -> None:
        key = self.combo_line_ending.currentData()
        if not key or key == self._rx_parser.mode.key:
            return
        self._flush_rx_parser()
        self._rx_parser.set_mode(str(key))
        self._queue_save_settings()

    # ---------------------------------------------------------- persistence #
    def _load_settings(self) -> None:
        blocker = QSignalBlocker(self.mgr)
        port = self._settings.value("connection/port", "")
        self._preferred_port = port if isinstance(port, str) else ""
        try:
            baud = int(self._settings.value("connection/baud", 115200))
        except (TypeError, ValueError):
            baud = 115200
        if baud in BAUD_RATES:
            self.combo_baud.setCurrentText(str(baud))

        for key, default, setter in (
            ("connection/dtr", True, self._toggle_dtr),
            ("connection/auto_reconnect", False, self._toggle_auto_reconnect),
            ("terminal/auto_clear", False, self._toggle_auto_clear),
            ("terminal/timestamps", False, self._toggle_timestamps),
            ("terminal/autoscroll", True, self._toggle_autoscroll),
        ):
            value = self._settings.value(key, default)
            if isinstance(value, (bool, int)):
                checked = bool(value)
            elif isinstance(value, str) and value.lower() in ("true", "false", "1", "0"):
                checked = value.lower() in ("true", "1")
            else:
                checked = default
            setter(checked)

        mode = self._settings.value("terminal/line_ending", DEFAULT_LINE_ENDING)
        index = self.combo_line_ending.findData(mode)
        if index >= 0:
            self.combo_line_ending.setCurrentIndex(index)
        self.tx_input.set_history(self._settings.value("terminal/history", []))
        geometry = self._settings.value("window/geometry")
        if isinstance(geometry, QByteArray):
            self.restoreGeometry(geometry)
        blocker.unblock()

    def _queue_save_settings(self, *_args) -> None:
        if not self._restoring_settings:
            self._settings_timer.start()

    def _save_settings(self) -> None:
        values = {
            "connection/port": self._selected_port() or self._preferred_port,
            "connection/baud": int(self.combo_baud.currentText()),
            "connection/dtr": self.mgr.dtr,
            "connection/auto_reconnect": self.mgr.auto_reconnect,
            "terminal/auto_clear": self._auto_clear,
            "terminal/timestamps": self.act_timestamp.isChecked(),
            "terminal/autoscroll": self.act_autoscroll.isChecked(),
            "terminal/line_ending": self.combo_line_ending.currentData(),
            "terminal/history": self.tx_input.history,
            "window/geometry": self.saveGeometry(),
        }
        for key, value in values.items():
            self._settings.setValue(key, value)
        self._settings.sync()
        if (self._settings.status() != QSettings.NoError
                and not self._settings_error_reported):
            self._settings_error_reported = True
            self._on_status("Could not save settings: %s" % self._settings.fileName())

    def _port_selection_changed(self, *_args) -> None:
        port = self._selected_port()
        if port:
            self._preferred_port = port
        self._queue_save_settings()

    # ------------------------------------------------------------ actions #
    def toggle_connect(self) -> None:
        if self.mgr.connection_requested:
            self._flush_rx_parser()
            self.mgr.disconnect()
            self._update_status()
            return
        port = self._selected_port()
        if not port:
            self._on_status("No port selected")
            return
        baud = int(self.combo_baud.currentText())
        self.mgr.configure(port, baud)
        self.mgr.connect()
        self._update_status()

    def send(self) -> None:
        text = self.tx_input.text()
        if not text:
            return
        data = text.encode("utf-8") + self._rx_parser.mode.tx_suffix
        written = self.mgr.write(data)
        if written < 0:
            self._on_status("TX failed - disconnected or serial error; input retained")
            return
        if written != len(data):
            self._on_status("TX incomplete (%d/%d bytes); input retained" %
                            (written, len(data)))
            return
        self.terminal.finish_line("rx")
        self.terminal.append_text(text + "\n", "tx")
        self.tx_input.remember(text)
        self.tx_input.clear()

    def clear_terminal(self) -> None:
        self._clear_terminal_state()
        self._on_status("Terminal cleared")

    def clear_command_history(self) -> None:
        self.tx_input.clear_history()
        self._save_settings()
        self._on_status("Command history and completion memory cleared")

    def _clear_terminal_state(self) -> None:
        self.terminal.clear_terminal()
        self._rx_parser.reset()
        self._rx_record_open = False

    def _flush_rx_parser(self) -> None:
        partial = self._rx_parser.flush()
        if partial:
            self.terminal.append_text(
                partial,
                "rx",
                timestamp_lines=False,
                timestamp_start=not self._rx_record_open,
            )
        self.terminal.finish_line("rx")
        self._rx_record_open = False

    def copy_terminal(self) -> None:
        QApplication.clipboard().setText(self.terminal.toPlainText())
        self._on_status("Terminal copied to clipboard")

    def export_txt(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export terminal to TXT", "serial_monitor.log",
            "Text files (*.txt);;All files (*)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(self.terminal.toPlainText())
            self._on_status("Exported: %s" % path)
        except OSError as e:
            QMessageBox.critical(self, "Export failed", str(e))

    # ---- port selection helpers ----------------------------------------- #
    @staticmethod
    def _port_display(p: PortInfo) -> str:
        """Human friendly combo label: 'COM9 - USB-SERIAL CH340'."""
        if p.description:
            return "%s - %s" % (p.device, p.description)
        return p.device

    def _selected_port(self) -> str:
        """Return the device string of the currently selected item."""
        data = self.combo_port.currentData()
        if data:
            return str(data)
        return ""

    def refresh_ports(self) -> None:
        current = self._selected_port() or self._preferred_port
        blocker = QSignalBlocker(self.combo_port)
        self.combo_port.clear()
        ports = available_ports()
        for p in ports:
            self.combo_port.addItem(self._port_display(p), p.device)
            self.combo_port.setItemData(
                self.combo_port.count() - 1, p.description,
                Qt.ItemDataRole.ToolTipRole)
        if current:
            idx = self.combo_port.findData(current)
            if idx < 0:
                self.combo_port.addItem("%s (unavailable)" % current, current)
                idx = self.combo_port.count() - 1
                self.combo_port.setItemData(
                    idx, "Remembered port. Connect with Auto Reconnect to wait for it.",
                    Qt.ItemDataRole.ToolTipRole)
            self.combo_port.setCurrentIndex(idx)
        else:
            self._select_default_port(ports)
        blocker.unblock()
        self._port_selection_changed()

    def _select_default_port(self, ports: list[PortInfo]) -> None:
        if not ports:
            return
        prefs = ("usb", "ch340", "ftdi", "cp210", "wch")
        for p in ports:
            if any(k in p.description.lower() for k in prefs):
                self.combo_port.setCurrentIndex(self.combo_port.findData(p.device))
                return
        self.combo_port.setCurrentIndex(0)

    # ------------------------------------------------------------ signals #
    def _on_serial_event(self, request_id: int, kind: str, payload) -> None:
        if request_id == self.mgr.request_id:
            self._serial_handlers[kind](payload)

    def _on_data(self, data: bytes) -> None:
        parse_lines = self._rx_parser.mode.rx_delimiter is not None
        for fragment in self._rx_parser.feed(data):
            self.tx_input.add_reference(fragment.text)
            self.terminal.append_text(
                fragment.text,
                "rx",
                timestamp_lines=not parse_lines,
                timestamp_start=not self._rx_record_open,
            )
            if parse_lines:
                self._rx_record_open = not fragment.complete

    def _on_connected(self, port: str) -> None:
        if self._auto_clear:
            self._clear_terminal_state()
        self._rx_parser.reset()
        self._rx_record_open = False
        self._on_status("Connected %s @ %s" % (port, self.mgr.baudrate))
        self._update_status()

    def _on_disconnected(self, reason: str) -> None:
        self._flush_rx_parser()
        self._on_status("Disconnected (%s)" % reason)
        self._update_status()

    def _on_status(self, msg: str) -> None:
        if self._restoring_settings:
            return
        self.terminal.finish_line("rx")
        self.terminal.append_text("[%s]\n" % msg, "sys")

    def _update_status(self) -> None:
        open_ = self.mgr.is_open
        pending = self.mgr.connection_requested and not open_
        text = "Disconnect" if open_ else "Cancel Retry" if pending else "Connect"
        self.btn_connect.setText(text)
        self.btn_connect.setChecked(open_ or pending)
        self.act_connect.setText(text)
        glyph = icon("unplug" if open_ or pending else "plug")
        self.btn_connect.setIcon(glyph)
        self.act_connect.setIcon(glyph)
        self.combo_port.setEnabled(not (open_ or pending))
        self.combo_baud.setEnabled(not (open_ or pending))

        col = PALETTE["success"] if open_ else PALETTE["warn"] if pending else PALETTE["text_muted"]
        self.label_status.setText("Online" if open_ else "Connecting / retrying" if pending else "Offline")
        self.label_dot.setToolTip(self.label_status.text())
        self.label_dot.setStyleSheet(
            "background: %s; border-radius: 4px;" % col)
        self.label_status.setStyleSheet(
            "color: %s; background: transparent; font-size: 12px; font-weight: 600;" % col)
        self.label_counters.setText("RX %d   TX %d" % (self.mgr.rx_count, self.mgr.tx_count))
        self.label_dtr.setText("DTR %s" % ("on" if self.mgr.dtr else "off"))
        port = self.mgr.port if open_ or pending else self._selected_port()
        baud = self.mgr.baudrate if open_ or pending else self.combo_baud.currentText()
        self.label_port.setText("%s @ %s" % (port, baud))
        self.btn_dtr.setChecked(self.mgr.dtr)

    # -------------------------------------------------------------- misc #
    def _about(self) -> None:
        AboutDialog(self).exec()

    def _show_shortcuts(self) -> None:
        shortcuts = ["%s: %s" % (
            action.shortcut().toString(QKeySequence.NativeText),
            action.text().replace("&", "")) for action in self._shortcut_actions]
        shortcuts.extend([
            "Alt+P / Alt+B / Alt+E: Focus port / baud / line ending",
            "Enter: Send typed input (does not execute suggestions)",
            "Up / Down: Browse sent commands; Down restores your draft",
            "Tab: Accept completion from command or received-text memory",
            "Ctrl+Space: Show suggestions; Esc: Dismiss suggestions",
            "Ctrl+C: Copy selected text; Ctrl+V: Paste into command input",
        ])
        dialog = QDialog(self, Qt.Dialog | Qt.FramelessWindowHint)
        dialog.setObjectName("keyboardShortcutsDialog")
        dialog.setWindowTitle("Keyboard Shortcuts")
        dialog.setModal(True)
        dialog.setAttribute(Qt.WA_StyledBackground)
        dialog.setStyleSheet(
            "QDialog#keyboardShortcutsDialog { background-color: %s; color: %s; }"
            % (PALETTE["bg"], PALETTE["text"]))
        dialog.resize(600, min(620, self.screen().availableGeometry().height() - 80))

        root = QVBoxLayout(dialog)
        root.setContentsMargins(12, 10, 12, 12)
        root.setSpacing(10)
        titlebar = FramelessTitleBar(dialog, "Keyboard Shortcuts")
        titlebar.btn_min.hide()
        titlebar.btn_max.hide()
        root.addWidget(titlebar)

        content = QLabel("\n".join(shortcuts))
        content.setObjectName("shortcutList")
        content.setTextFormat(Qt.PlainText)
        content.setWordWrap(True)
        content.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        content.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        content.setContentsMargins(12, 8, 12, 8)
        scroll = QScrollArea()
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        root.addWidget(scroll, 1)

        footer = QHBoxLayout()
        footer.addStretch(1)
        close = NeumorphicButton("Close", accent=True)
        close.setToolTip("Close keyboard shortcuts (Esc)")
        close.clicked.connect(dialog.accept)
        footer.addWidget(close)
        root.addLayout(footer)
        close.setFocus()
        dialog.exec()

    # ---------------------------------------------------- frameless chrome #
    RESIZE_MARGIN = 6

    def showEvent(self, event) -> None:   # noqa: N802
        super().showEvent(event)
        if not self._state_connected:
            handle = self.windowHandle()
            if handle is not None:
                handle.windowStateChanged.connect(self._sync_titlebar)
                self._state_connected = True
        self.titlebar.update_state(self.isMaximized())

    def _sync_titlebar(self, *_args) -> None:
        self.titlebar.update_state(self.isMaximized())

    def _edge_at(self, gp) -> Qt.Edges:
        """Return the window edges the logical global point ``gp`` falls on."""
        local = self.mapFromGlobal(gp)
        m = self.RESIZE_MARGIN
        w, h = self.width(), self.height()
        edges = Qt.Edges()
        if local.y() <= m:
            edges |= Qt.TopEdge
        if local.y() >= h - m:
            edges |= Qt.BottomEdge
        if local.x() <= m:
            edges |= Qt.LeftEdge
        if local.x() >= w - m:
            edges |= Qt.RightEdge
        return edges

    def _point_over_win_button(self, gp) -> bool:
        for btn in (self.titlebar.btn_min, self.titlebar.btn_max,
                    self.titlebar.btn_close):
            if btn.isVisible():
                tl = btn.mapToGlobal(btn.rect().topLeft())
                if btn.rect().translated(tl).contains(gp):
                    return True
        return False

    @staticmethod
    def _resize_cursor(edges) -> Qt.CursorShape:
        top = edges & Qt.TopEdge
        bottom = edges & Qt.BottomEdge
        left = edges & Qt.LeftEdge
        right = edges & Qt.RightEdge
        if (top and left) or (bottom and right):
            return Qt.SizeFDiagCursor
        if (top and right) or (bottom and left):
            return Qt.SizeBDiagCursor
        if top or bottom:
            return Qt.SizeVerCursor
        if left or right:
            return Qt.SizeHorCursor
        return Qt.ArrowCursor

    def eventFilter(self, obj, event):
        if isinstance(obj, QWidget) and obj.window() is self:
            et = event.type()
            handle = self.windowHandle()
            if handle is not None and not self.isMaximized():
                if et == QEvent.MouseMove:
                    gp = QCursor.pos()
                    if self._point_over_win_button(gp):
                        self.unsetCursor()
                    else:
                        edges = self._edge_at(gp)
                        self.setCursor(self._resize_cursor(edges)) if edges else self.unsetCursor()
                elif et == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                    gp = QCursor.pos()
                    if self._point_over_win_button(gp):
                        return False  # the window control handles it
                    edges = self._edge_at(gp)
                    if edges:
                        handle.startSystemResize(edges)
                        return True
        return super().eventFilter(obj, event)

    def closeEvent(self, event) -> None:   # noqa: N802
        self._timer.stop()
        self._settings_timer.stop()
        self._save_settings()
        self.mgr.stop()
        QApplication.instance().removeEventFilter(self)
        event.accept()


def main() -> int:
    app = QApplication(sys.argv)
    app.setOrganizationName("SerMon")
    app.setApplicationName("SerialMonitor")
    app.setApplicationVersion(APP_VERSION)
    app.setWindowIcon(QIcon(str(APP_ICON_PATH)))
    load_bundled_fonts()
    app.setFont(QFont(UI_FONT, UI_FONT_SIZE, UI_WEIGHT))
    app.setStyleSheet(build_qss())
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())



