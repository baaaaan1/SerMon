"""Serial Monitor - a neumorphism dark-mode serial port monitor.

Run from the project root::

    python main.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt, QEvent, QTimer
from PySide6.QtGui import QAction, QKeySequence, QFont, QCursor, QIcon
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QComboBox, QLineEdit, QFileDialog, QMessageBox, QMenuBar, QSizePolicy,
)

from theme import PALETTE, build_qss, load_bundled_fonts, UI_FONT, UI_FONT_SIZE, UI_WEIGHT
from serial_engine import SerialManager, available_ports, PortInfo
from widgets import NeumorphicButton, NeumorphicFrame, TerminalView
from frameless import FramelessTitleBar


BAUD_RATES = [300, 1200, 2400, 4800, 9600, 19200, 38400, 57600,
              115200, 230400, 460800, 921600]
APP_ICON_PATH = Path(__file__).resolve().parent / "assets" / "app_icon.ico"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Serial Monitor")
        self.setWindowIcon(QIcon(str(APP_ICON_PATH)))
        # Frameless: the native caption is replaced by our themed title bar.
        self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_StyledBackground)
        self.resize(1000, 680)

        self.mgr = SerialManager(self)
        self._auto_clear = False
        self._guard = False   # re-entrancy guard for toggle synchronisation

        self._build_menu()
        self._build_ui()
        self._wire()

        self.terminal.append_text("Serial Monitor ready.\n", "sys")
        self.refresh_ports()
        self._select_default_port()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_status)
        self._timer.start(250)

        self._state_connected = False
        QApplication.instance().installEventFilter(self)

    # ------------------------------------------------------------------ menu #
    def _build_menu(self) -> None:
        bar = QMenuBar()
        self.menu_bar = bar
        bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        m_file = bar.addMenu("&File")
        act_export = QAction("Export to TXT...", self)
        act_export.setShortcut(QKeySequence("Ctrl+E"))
        act_export.triggered.connect(self.export_txt)
        m_file.addAction(act_export)

        act_copy = QAction("Copy Terminal", self)
        act_copy.setShortcut(QKeySequence("Ctrl+Shift+C"))
        act_copy.triggered.connect(self.copy_terminal)
        m_file.addAction(act_copy)

        m_file.addSeparator()
        act_quit = QAction("Quit", self)
        act_quit.setShortcut(QKeySequence.Quit)
        act_quit.triggered.connect(self.close)
        m_file.addAction(act_quit)

        m_conn = bar.addMenu("&Connection")
        self.act_connect = QAction("Connect", self)
        self.act_connect.setShortcut(QKeySequence("Ctrl+Return"))
        self.act_connect.triggered.connect(self.toggle_connect)
        m_conn.addAction(self.act_connect)

        self.act_dtr = QAction("DTR (Data Terminal Ready)", self)
        self.act_dtr.setCheckable(True)
        self.act_dtr.setChecked(True)
        self.act_dtr.toggled.connect(self._toggle_dtr)
        m_conn.addAction(self.act_dtr)

        m_conn.addSeparator()
        self.act_auto_reconnect = QAction("Auto-Reconnect", self)
        self.act_auto_reconnect.setCheckable(True)
        self.act_auto_reconnect.toggled.connect(self._toggle_auto_reconnect)
        m_conn.addAction(self.act_auto_reconnect)

        self.act_auto_clear = QAction("Auto-Clear on Reconnect", self)
        self.act_auto_clear.setCheckable(True)
        self.act_auto_clear.toggled.connect(self._toggle_auto_clear)
        m_conn.addAction(self.act_auto_clear)

        m_view = bar.addMenu("&View")
        act_refresh = QAction("Refresh Ports", self)
        act_refresh.setShortcut(QKeySequence("F5"))
        act_refresh.triggered.connect(self.refresh_ports)
        m_view.addAction(act_refresh)

        self.act_autoscroll = QAction("Auto-Scroll", self)
        self.act_autoscroll.setCheckable(True)
        self.act_autoscroll.setChecked(True)
        self.act_autoscroll.toggled.connect(self._toggle_autoscroll)
        m_view.addAction(self.act_autoscroll)

        self.act_timestamp = QAction("Timestamps", self)
        self.act_timestamp.setCheckable(True)
        self.act_timestamp.setShortcut(QKeySequence("Ctrl+T"))
        self.act_timestamp.toggled.connect(self._toggle_timestamps)
        m_view.addAction(self.act_timestamp)

        act_clear = QAction("Clear Terminal", self)
        act_clear.setShortcut(QKeySequence("Ctrl+L"))
        act_clear.triggered.connect(self.clear_terminal)
        m_view.addAction(act_clear)

        m_help = bar.addMenu("&Help")
        act_about = QAction("About", self)
        act_about.triggered.connect(self._about)
        m_help.addAction(act_about)

    # ------------------------------------------------------------------- ui #
    def _label(self, text: str) -> QLabel:
        """A muted label used across the bars."""
        lbl = QLabel(text)
        lbl.setStyleSheet("color: %s; background: transparent;" % PALETTE["text_muted"])
        return lbl

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

        # ---------------- top toolbar tray ---------------- #
        self.toolbar = NeumorphicFrame(radius=16)
        tb = QHBoxLayout(self.toolbar)
        tb.setContentsMargins(14, 8, 14, 8)
        tb.setSpacing(8)
        tb.addWidget(self._label("Port"))
        self.combo_port = QComboBox()
        self.combo_port.setMinimumWidth(104)
        tb.addWidget(self.combo_port)
        self.btn_refresh = NeumorphicButton("Refresh")
        tb.addWidget(self.btn_refresh)
        tb.addSpacing(8)
        tb.addWidget(self._label("Baud"))
        self.combo_baud = QComboBox()
        for b in BAUD_RATES:
            self.combo_baud.addItem(str(b))
        self.combo_baud.setCurrentText("115200")
        self.combo_baud.setMinimumWidth(110)
        tb.addWidget(self.combo_baud)
        tb.addSpacing(8)
        self.btn_connect = NeumorphicButton("Connect", accent=True, toggle=True)
        tb.addWidget(self.btn_connect)
        self.btn_dtr = NeumorphicButton("DTR", toggle=True)
        self.btn_dtr.setChecked(True)
        tb.addWidget(self.btn_dtr)
        self.btn_reconnect = NeumorphicButton("Reconnect", toggle=True)
        tb.addWidget(self.btn_reconnect)
        self.btn_auto_clear = NeumorphicButton("AutoClear", toggle=True)
        tb.addWidget(self.btn_auto_clear)
        self.btn_timestamp = NeumorphicButton("TimeSt", toggle=True)
        self.btn_timestamp.setToolTip("Show / hide timestamps")
        tb.addWidget(self.btn_timestamp)
        tb.addStretch(1)
        root.addWidget(self.toolbar)

        # ---------------- terminal tray ---------------- #
        self.term_frame = NeumorphicFrame(radius=16)
        tfl = QVBoxLayout(self.term_frame)
        tfl.setContentsMargins(10, 10, 10, 10)
        self.terminal = TerminalView()
        tfl.addWidget(self.terminal)
        root.addWidget(self.term_frame, 1)

        # ---------------- bottom bar tray ---------------- #
        self.bottom = NeumorphicFrame(radius=16)
        bl = QVBoxLayout(self.bottom)
        bl.setContentsMargins(14, 8, 14, 8)
        bl.setSpacing(8)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.tx_input = QLineEdit()
        self.tx_input.setPlaceholderText("Type data to send...")
        row.addWidget(self.tx_input, 1)
        self.btn_send = NeumorphicButton("Send", accent=True)
        row.addWidget(self.btn_send)
        self.btn_clear = NeumorphicButton("Clear")
        row.addWidget(self.btn_clear)
        self.btn_copy = NeumorphicButton("Copy")
        row.addWidget(self.btn_copy)
        self.btn_export = NeumorphicButton("Export")
        row.addWidget(self.btn_export)
        bl.addLayout(row)

        srow = QHBoxLayout()
        srow.setSpacing(12)
        self.label_dot = QLabel("○")
        self.label_status = QLabel("Offline")
        self.label_counters = QLabel("RX 0   TX 0")
        self.label_dtr = QLabel("DTR on")
        self.label_port = QLabel("")
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
        self.mgr.data_received.connect(self._on_data)
        self.mgr.connected.connect(self._on_connected)
        self.mgr.disconnected.connect(self._on_disconnected)
        self.mgr.status_changed.connect(self._on_status)

        self.btn_refresh.clicked.connect(self.refresh_ports)
        self.btn_connect.clicked.connect(self.toggle_connect)

        self.act_dtr.toggled.connect(self._toggle_dtr)
        self.act_auto_reconnect.toggled.connect(self._toggle_auto_reconnect)
        self.act_auto_clear.toggled.connect(self._toggle_auto_clear)
        self.act_autoscroll.toggled.connect(self._toggle_autoscroll)

        self.btn_dtr.toggled.connect(self._toggle_dtr)
        self.btn_reconnect.toggled.connect(self._toggle_auto_reconnect)
        self.btn_auto_clear.toggled.connect(self._toggle_auto_clear)
        self.btn_timestamp.toggled.connect(self._toggle_timestamps)

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

    def _toggle_auto_reconnect(self, checked) -> None:
        if self._guard:
            return
        self.mgr.set_auto_reconnect(checked)
        self._sync_toggle(self.act_auto_reconnect, self.btn_reconnect, checked)

    def _toggle_auto_clear(self, checked) -> None:
        if self._guard:
            return
        self._auto_clear = bool(checked)
        self._sync_toggle(self.act_auto_clear, self.btn_auto_clear, checked)

    def _toggle_autoscroll(self, checked) -> None:
        if self._guard:
            return
        self.terminal.set_follow(checked)
        self._sync_toggle(self.act_autoscroll, None, checked)

    def _toggle_timestamps(self, checked) -> None:
        if self._guard:
            return
        self.terminal.set_timestamps(bool(checked))
        self._sync_toggle(self.act_timestamp, self.btn_timestamp, checked)

    # ------------------------------------------------------------ actions #
    def toggle_connect(self) -> None:
        if self.mgr.is_open:
            self.mgr.disconnect()
            return
        port = self._selected_port()
        if not port:
            self._on_status("No port selected")
            return
        baud = int(self.combo_baud.currentText())
        self.mgr.configure(port, baud)
        self.mgr.connect()

    def send(self) -> None:
        text = self.tx_input.text()
        if not text:
            return
        data = text.encode("utf-8")
        if self.mgr.write(data) < 0:
            self._on_status("TX failed - not connected")
            return
        self.terminal.append_text(text + "\n", "tx")
        self.tx_input.clear()

    def clear_terminal(self) -> None:
        self.terminal.clear_terminal()
        self._on_status("Terminal cleared")

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
            with open(path, "w", encoding="utf-8") as f:
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
        current = self._selected_port()
        self.combo_port.clear()
        ports = available_ports()
        for p in ports:
            self.combo_port.addItem(self._port_display(p), p.device)
            self.combo_port.setItemData(
                self.combo_port.count() - 1, p.description,
                Qt.ItemDataRole.ToolTipRole)
        if ports and current:
            idx = self.combo_port.findData(current)
            if idx >= 0:
                self.combo_port.setCurrentIndex(idx)

    def _select_default_port(self) -> None:
        ports = available_ports()
        if not ports:
            return
        prefs = ("usb", "ch340", "ftdi", "cp210", "wch")
        for p in ports:
            if any(k in p.description.lower() for k in prefs):
                self.combo_port.setCurrentIndex(self.combo_port.findData(p.device))
                return
        self.combo_port.setCurrentIndex(0)

    # ------------------------------------------------------------ signals #
    def _on_data(self, data: bytes) -> None:
        self.terminal.append_text(data.decode("utf-8", "replace"), "rx")

    def _on_connected(self, port: str) -> None:
        self._on_status("Connected %s @ %s" % (port, self.combo_baud.currentText()))
        if self._auto_clear:
            self.terminal.clear_terminal()

    def _on_disconnected(self, reason: str) -> None:
        self._on_status("Disconnected (%s)" % reason)

    def _on_status(self, msg: str) -> None:
        self.terminal.append_text("[%s]\n" % msg, "sys")

    def _update_status(self) -> None:
        open_ = self.mgr.is_open
        self.btn_connect.setText("Disconnect" if open_ else "Connect")
        self.btn_connect.setChecked(open_)
        self.act_connect.setText("Disconnect" if open_ else "Connect")

        col = PALETTE["success"] if open_ else PALETTE["text_muted"]
        self.label_dot.setText("●" if open_ else "○")
        self.label_status.setText("Online" if open_ else "Offline")
        self.label_dot.setStyleSheet(
            "color: %s; background: transparent; font-size: 12px;" % col)
        self.label_status.setStyleSheet(
            "color: %s; background: transparent; font-size: 12px; font-weight: 600;" % col)
        self.label_counters.setText("RX %d   TX %d" % (self.mgr.rx_count, self.mgr.tx_count))
        self.label_dtr.setText("DTR %s" % ("on" if self.mgr.dtr else "off"))
        self.label_port.setText("%s @ %s" % (self._selected_port(),
                                             self.combo_baud.currentText()))
        self.btn_dtr.setChecked(self.mgr.dtr)

    # -------------------------------------------------------------- misc #
    def _about(self) -> None:
        QMessageBox.about(
            self, "About Serial Monitor",
            "<b>Serial Monitor</b><br>Neumorphism dark-mode serial port monitor."
            "<br>PySide6 + pyserial.")

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
        self.mgr.stop()
        event.accept()


def main() -> int:
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(str(APP_ICON_PATH)))
    load_bundled_fonts()
    app.setFont(QFont(UI_FONT, UI_FONT_SIZE, UI_WEIGHT))
    app.setStyleSheet(build_qss())
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())



