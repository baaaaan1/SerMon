"""Main application window."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QActionGroup, QKeySequence
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QSizePolicy,
    QSplitter,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from serial_engine.config import SerialConfigError, SerialSessionConfig
from serial_engine.line_control import LineControlCommand, parse_line_control_command
from serial_engine.port_scanner import PortInfo
from serial_engine.protocols import ProtocolParser, registry
from services.config import AppConfig

from .bridge import SerialBridge
from .models import DEFAULT_MAX_LINES, LINE_ENDINGS, SCROLLBACK_LIMITS
from .state import AppState
from .theme import THEME_MODES, ThemeManager, get_theme_manager
from .widgets import (
    ActivityIndicator,
    ConnectionPanel,
    QuickCommands,
    StatusDot,
    TxInput,
)
from .widgets.counters import ByteCounter
from .widgets.terminal import TerminalView

logger = logging.getLogger(__name__)

#: Services-config ``parity`` field (pyserial char) -> display label.
_PARITY_TO_DISPLAY = {"N": "None", "E": "Even", "O": "Odd", "M": "Mark", "S": "Space"}

#: Default window size when no geometry is persisted.
DEFAULT_SIZE = (840, 560)


def _fmt_onoff(value: bool | None) -> str:
    """Format a line level as ``ON``/``OFF`` (``--`` when unset)."""
    if value is True:
        return "ON"
    if value is False:
        return "OFF"
    return "--"


def _noop() -> None:
    """Default no-op persistence callback (used when no config/save is wired)."""


class MainWindow(QMainWindow):
    """Top-level window that wires the UI widgets to the serial bridge.

    Note that this class only ever talks to :class:`SerialBridge` (Qt signals);
    it never imports or invokes pyserial directly.
    """

    def __init__(
        self,
        bridge: SerialBridge,
        config: AppConfig | None = None,
        save: Callable[[], None] | None = None,
        theme_manager: ThemeManager | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._bridge = bridge
        self._state = AppState()
        self._config = config if config is not None else AppConfig()
        self._save = save if save is not None else _noop
        self._theme_manager = theme_manager if theme_manager is not None else get_theme_manager()
        # Suppress persistence while the initial UI state is populated.
        self._loading = True
        self._maximized_applied = False
        self._parser: ProtocolParser | None = None
        #: Duplicate-send guard state (text + monotonic timestamp of last send).
        self._last_sent_text: str | None = None
        self._last_sent_time: float = 0.0
        #: Window (ms) during which an identical resend is treated as accidental.
        self._duplicate_debounce_ms: float = 300.0
        self.setWindowTitle("Serial Monitor")
        self._restore_geometry()
        self._build_ui()
        self._connect_signals()
        self._load_config_into_ui()
        self.refresh_ports()
        self._select_parser(self._parser_combo.currentText())
        self._restore_port()
        self._update_controls()
        self._refresh_line_state()
        self._loading = False

    # -- Persistence ---------------------------------------------------------

    def _persist(self) -> None:
        """Write the current live config to disk via the save callback."""
        self._save()

    def _restore_geometry(self) -> None:
        """Apply persisted window position/size before the widgets are built."""
        window = self._config.window
        if window.width > 0 and window.height > 0:
            self.resize(window.width, window.height)
        else:
            self.resize(*DEFAULT_SIZE)
        if window.x >= 0 and window.y >= 0:
            self.move(window.x, window.y)

    def _save_geometry(self) -> None:
        """Capture the current geometry into the config and persist it."""
        if self._loading:
            return
        window = self._config.window
        geom = self.geometry()
        window.x = geom.x()
        window.y = geom.y()
        window.width = geom.width()
        window.height = geom.height()
        window.maximized = self.isMaximized()
        self._persist()

    def _load_config_into_ui(self) -> None:
        """Apply saved baud/parser/line settings to the connection controls."""
        cfg = self._config
        # Baud rate (append a custom value so an arbitrary saved baud survives).
        baud = str(cfg.serial.baudrate)
        if self._baud_combo.findText(baud) < 0:
            self._baud_combo.addItem(baud)
        self._baud_combo.setCurrentText(baud)
        # Parser (fall back to the default if the saved parser no longer exists).
        if cfg.parser in registry.names():
            self._parser_combo.setCurrentText(cfg.parser)
        else:
            cfg.parser = "line"
            self._parser_combo.setCurrentText("line")
        # Advanced line settings (services config stores pyserial-style values).
        self._data_bits_combo.setCurrentIndex(
            self._data_bits_combo.findData(cfg.serial.bytesize)
        )
        self._parity_combo.setCurrentText(_PARITY_TO_DISPLAY.get(cfg.serial.parity, "None"))
        self._stop_bits_combo.setCurrentIndex(
            self._stop_bits_combo.findData(cfg.serial.stopbits)
        )
        # Line control (DTR/RTS) may be unset; leave the toggle at its default.
        if cfg.serial.dtr is not None:
            self._dtr_check.setChecked(cfg.serial.dtr)
        if cfg.serial.rts is not None:
            self._rts_check.setChecked(cfg.serial.rts)
        # Reconnect settings (apply to the engine so a later connect honours them).
        reconnect_enabled = bool(cfg.reconnect_enabled)
        self._reconnect_check.setChecked(reconnect_enabled)
        self._reconnect_interval_spin.setValue(max(0.5, float(cfg.reconnect_interval)))
        self._bridge.set_reconnect_enabled(reconnect_enabled)
        self._bridge.set_reconnect_interval(float(cfg.reconnect_interval))

    def _restore_port(self) -> None:
        """Select the saved port in the combo after ports have been enumerated."""
        device = self._config.serial.port
        if not device:
            return
        index = self._port_combo.findData(device)
        if index >= 0:
            self._port_combo.setCurrentIndex(index)

    # -- UI construction ---------------------------------------------------

    def _build_ui(self) -> None:
        self._terminal = TerminalView()
        self._build_toolbar()
        self._build_theme_menu()

        central = QWidget(self)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._splitter = QSplitter(Qt.Orientation.Horizontal, central)
        self._splitter.setObjectName("mainSplitter")
        self._splitter.setHandleWidth(4)

        # Left sidebar: connection config + quick commands.
        self._connection = ConnectionPanel()
        self._port_combo = self._connection.port_combo
        self._refresh_btn = self._connection.refresh_btn
        self._baud_combo = self._connection.baud_combo
        self._data_bits_combo = self._connection.data_bits_combo
        self._parity_combo = self._connection.parity_combo
        self._stop_bits_combo = self._connection.stop_bits_combo
        self._flow_combo = self._connection.flow_combo
        self._dtr_check = self._connection.dtr_check
        self._rts_check = self._connection.rts_check
        self._reconnect_check = self._connection.reconnect_check
        self._reconnect_interval_spin = self._connection.reconnect_interval_spin
        self._connect_btn = self._connection.connect_btn

        self._quick = QuickCommands()

        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(10, 10, 10, 10)
        sidebar_layout.setSpacing(12)
        sidebar_layout.addWidget(self._connection)
        sidebar_layout.addWidget(self._quick, 1)
        self._splitter.addWidget(sidebar)

        # Right: terminal.
        terminal_holder = QWidget()
        terminal_holder.setObjectName("terminalHolder")
        terminal_layout = QVBoxLayout(terminal_holder)
        terminal_layout.setContentsMargins(10, 10, 10, 10)
        terminal_layout.addWidget(self._terminal)
        self._splitter.addWidget(terminal_holder)

        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)
        self._splitter.setSizes([270, 570])
        root.addWidget(self._splitter, 1)

        # TX input row (single/multiline command input + send/re-send/clear).
        self._tx_input = TxInput()
        self._input = self._tx_input.single_input
        self._send_btn = self._tx_input.send_btn
        self._clear_btn = self._tx_input.clear_btn
        send_bar = QHBoxLayout()
        send_bar.setContentsMargins(10, 6, 10, 8)
        send_bar.setSpacing(6)
        send_bar.addWidget(self._tx_input, 1)
        root.addLayout(send_bar)

        self.setCentralWidget(central)
        self._build_status_bar()

    def _build_toolbar(self) -> None:
        """Build the top toolbar (parser, terminal options, connect/clear/refresh)."""
        tb = QToolBar("App", self)
        tb.setObjectName("mainToolbar")
        tb.setMovable(False)
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.addToolBar(tb)
        self._toolbar = tb

        title = QLabel("Serial Monitor", tb)
        title.setObjectName("appTitle")
        tb.addWidget(title)
        tb.addSeparator()

        tb.addWidget(QLabel("Parser:", tb))
        self._parser_combo = QComboBox(tb)
        for name in registry.names():
            self._parser_combo.addItem(name)
        self._parser_combo.setCurrentText("line")
        self._parser_combo.setToolTip("Decode incoming data as this protocol.")
        tb.addWidget(self._parser_combo)
        tb.addSeparator()

        self._timestamp_check = self._make_toggle(
            tb, "Timestamp", "Prefix each received line with a timestamp.", True
        )
        self._autoscroll_check = self._make_toggle(
            tb, "Autoscroll", "Keep scrolling to the newest data.", True
        )
        self._clear_on_connect_check = self._make_toggle(
            tb, "Clear on connect", "Clear the terminal when a connection opens.", False
        )
        self._flow_markers_check = self._make_toggle(
            tb, "Flow markers", "Highlight TX/RX markers in the output.", True
        )
        self._eof_check = self._make_toggle(
            tb, "EOF marker", "Draw an end-of-line marker when the port closes.", True
        )

        tb.addSeparator()
        self._pause_check = self._make_toggle(
            tb, "Pause", "Pause the on-screen output (received data keeps buffering).", False
        )
        self._wrap_check = self._make_toggle(
            tb, "Wrap", "Wrap long lines to the terminal width.", True
        )

        tb.addWidget(QLabel("Max lines:", tb))
        self._max_lines_combo = QComboBox(tb)
        for limit in SCROLLBACK_LIMITS:
            self._max_lines_combo.addItem("Unlimited" if limit == 0 else str(limit), limit)
        self._max_lines_combo.setCurrentIndex(SCROLLBACK_LIMITS.index(DEFAULT_MAX_LINES))
        self._max_lines_combo.setToolTip(
            "Limit the number of buffered lines; the oldest lines are dropped."
        )
        tb.addWidget(self._max_lines_combo)

        tb.addWidget(QLabel("Line ending:", tb))
        self._line_ending_combo = QComboBox(tb)
        self._line_ending_combo.addItems(list(LINE_ENDINGS))
        self._line_ending_combo.setCurrentText("LF")
        self._line_ending_combo.setToolTip("Line ending appended to transmitted text.")
        tb.addWidget(self._line_ending_combo)

        spacer = QWidget(tb)
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        tb.addWidget(spacer)

        self._refresh_action = QAction("Refresh", tb)
        self._refresh_action.setShortcut(QKeySequence("F5"))
        self._refresh_action.setToolTip("Refresh the port list (F5).")
        self._refresh_action.triggered.connect(self.refresh_ports)
        tb.addAction(self._refresh_action)

        self._find_action = QAction("Find", tb)
        self._find_action.setShortcut(QKeySequence("Ctrl+F"))
        self._find_action.setToolTip("Find text in the terminal (Ctrl+F).")
        self._find_action.triggered.connect(self._terminal.toggle_find)
        tb.addAction(self._find_action)

        self._copy_all_action = QAction("Copy all", tb)
        self._copy_all_action.setShortcut(QKeySequence("Ctrl+Shift+C"))
        self._copy_all_action.setToolTip("Copy all terminal text (Ctrl+Shift+C).")
        self._copy_all_action.triggered.connect(self._terminal.copy_all)
        tb.addAction(self._copy_all_action)

        self._clear_action = QAction("Clear", tb)
        self._clear_action.setShortcut(QKeySequence("Ctrl+L"))
        self._clear_action.setToolTip("Clear the terminal output (Ctrl+L).")
        self._clear_action.triggered.connect(self._terminal.clear)
        tb.addAction(self._clear_action)

        self._connect_action = QAction("Connect", tb)
        self._connect_action.setShortcut(QKeySequence("Ctrl+Return"))
        self._connect_action.setToolTip("Connect / disconnect (Ctrl+Return).")
        self._connect_action.triggered.connect(self._toggle_connection)
        tb.addAction(self._connect_action)

    def _make_toggle(
        self,
        tb: QToolBar,
        text: str,
        tooltip: str,
        checked: bool,
    ) -> QAction:
        """Create a checkable toolbar action (terminal option toggle)."""
        action = QAction(text, tb)
        action.setCheckable(True)
        action.setChecked(checked)
        action.setToolTip(tooltip)
        tb.addAction(action)
        return action

    def _build_status_bar(self) -> None:
        """Build the status bar: state dot + message (left), activity + counters (right)."""
        status = self.statusBar()
        self._status_dot = StatusDot()
        self._status_label = QLabel("Disconnected")
        self._status_label.setObjectName("statusMessage")

        left = QWidget()
        left_layout = QHBoxLayout(left)
        left_layout.setContentsMargins(6, 2, 6, 2)
        left_layout.setSpacing(8)
        left_layout.addWidget(self._status_dot)
        left_layout.addWidget(self._status_label, 1)
        status.addWidget(left, 1)

        self._activity = ActivityIndicator()
        self._byte_counter = ByteCounter()
        self._line_state_label = QLabel("DTR: --   RTS: --")
        self._line_state_label.setObjectName("lineState")
        self._line_state_label.setToolTip("Live status of the DTR/RTS control lines.")
        status.addPermanentWidget(self._line_state_label)
        status.addPermanentWidget(self._byte_counter)
        status.addPermanentWidget(self._activity)


    def _build_theme_menu(self) -> None:
        """Add a View > Theme submenu so the theme can be switched and persisted."""
        view_menu = self.menuBar().addMenu("View")
        self._theme_menu = view_menu.addMenu("Theme")
        self._theme_group = QActionGroup(self)
        self._theme_group.setExclusive(True)
        self._theme_actions: dict[str, QAction] = {}
        for label, key in (("Light", "light"), ("Dark", "dark"), ("System", "system")):
            action = QAction(label, self)
            action.setCheckable(True)
            action.setData(key)
            action.triggered.connect(lambda _checked=False, k=key: self._set_theme(k))
            self._theme_group.addAction(action)
            self._theme_menu.addAction(action)
            self._theme_actions[key] = action

        # Set the action matching the persisted theme (fall back to System).
        selected = self._theme_actions.get(self._config.theme)
        if selected is None:
            self._config.theme = "system"
            selected = self._theme_actions["system"]
        selected.setChecked(True)

    def _set_theme(self, resolution: str) -> None:
        """Switch the theme, persist it, and keep the checked menu in sync."""
        if self._loading:
            return
        if resolution not in THEME_MODES:
            return
        if self._config.theme != resolution:
            self._config.theme = resolution
            self._persist()
        self._theme_manager.set_resolution(resolution)
        self._sync_theme_actions(resolution)

    def _sync_theme_actions(self, resolution: str) -> None:
        """Check the menu action that corresponds to *resolution*."""
        action = self._theme_actions.get(resolution)
        if action is not None:
            action.setChecked(True)

    def _connect_signals(self) -> None:
        self._connect_btn.clicked.connect(self._toggle_connection)
        self._refresh_btn.clicked.connect(self.refresh_ports)
        self._tx_input.send_requested.connect(self._send_input)
        self._tx_input.resend_requested.connect(self._send_resend)
        self._clear_btn.clicked.connect(self._terminal.clear)
        self._parser_combo.currentTextChanged.connect(self._select_parser)
        self._port_combo.currentIndexChanged.connect(self._on_port_changed)
        self._baud_combo.currentTextChanged.connect(self._on_baud_changed)
        self._dtr_check.toggled.connect(self._on_dtr_toggled)
        self._rts_check.toggled.connect(self._on_rts_toggled)
        self._reconnect_check.toggled.connect(self._on_reconnect_enabled_toggled)
        self._reconnect_interval_spin.valueChanged.connect(self._on_reconnect_interval_changed)

        self._timestamp_check.toggled.connect(self._update_options)
        self._autoscroll_check.toggled.connect(self._update_options)
        self._clear_on_connect_check.toggled.connect(self._update_options)
        self._flow_markers_check.toggled.connect(self._update_options)
        self._eof_check.toggled.connect(self._update_options)
        self._line_ending_combo.currentTextChanged.connect(self._update_options)
        self._pause_check.toggled.connect(self._terminal.set_paused)
        self._wrap_check.toggled.connect(self._terminal.set_word_wrap)
        self._max_lines_combo.currentIndexChanged.connect(self._on_max_lines_changed)
        self._update_options()

        self._quick.send_requested.connect(self._send_quick_command)

        self._bridge.data_received.connect(self._on_data)
        self._bridge.connection_changed.connect(self._on_connection)
        self._bridge.error_occurred.connect(self._on_error)
        self._bridge.ports_refreshed.connect(self._on_ports_refreshed)

    # -- Behaviour ----------------------------------------------------------

    def refresh_ports(self) -> None:
        """Ask the bridge to rescan; the drop-down updates on change via a signal."""
        self._bridge.refresh_ports()

    def _on_ports_refreshed(self, ports: list[PortInfo]) -> None:
        """Repopulate the port drop-down, preserving the user's selection.

        Signals are blocked while rebuilding so no spurious ``_on_port_changed``
        (and therefore no config save) fires.  If the previously selected port is
        still present it stays selected, otherwise the selection is cleared rather
        than silently jumping to a different device.
        """
        previous = self._port_combo.currentData()
        self._state.available_ports = list(ports)
        self._port_combo.blockSignals(True)
        try:
            self._port_combo.clear()
            for port in ports:
                self._port_combo.addItem(port.label, port.device)
            if previous is not None:
                index = self._port_combo.findData(previous)
                if index >= 0:
                    self._port_combo.setCurrentIndex(index)
                else:
                    self._port_combo.setCurrentIndex(-1)
            elif ports:
                self._port_combo.setCurrentIndex(0)
        finally:
            self._port_combo.blockSignals(False)
        logger.debug("Port list refreshed: %d port(s)", len(ports))

    def _toggle_connection(self) -> None:
        state = self._bridge.connection_state
        if state is ConnectionState.CONNECTED:
            self._bridge.disconnect_port()
            return
        if state.is_busy:
            return
        port = self._port_combo.currentData()
        if not port:
            self._on_error("Select a serial port first.")
            return
        try:
            baud = int(self._baud_combo.currentText())
        except ValueError:
            self._on_error("Baud rate must be a number.")
            return
        try:
            config = SerialSessionConfig(
                baudrate=baud,
                data_bits=int(self._data_bits_combo.currentData()),
                parity=self._parity_combo.currentText(),
                stop_bits=float(self._stop_bits_combo.currentData()),
                flow_control=self._flow_combo.currentText(),
                dtr=self._dtr_check.isChecked(),
                rts=self._rts_check.isChecked(),
            )
        except SerialConfigError as exc:
            self._on_error(str(exc))
            return
        self._bridge.connect_port(port, baudrate=baud, config=config)

    def _update_controls(self) -> None:
        """Enable/disable widgets based on the engine-owned connection state."""
        state = self._bridge.connection_state
        connected = state is ConnectionState.CONNECTED
        busy = state.is_busy
        editable = state.is_editable
        self._port_combo.setEnabled(editable)
        self._baud_combo.setEnabled(editable)
        self._parser_combo.setEnabled(editable)
        self._data_bits_combo.setEnabled(editable)
        self._parity_combo.setEnabled(editable)
        self._stop_bits_combo.setEnabled(editable)
        self._flow_combo.setEnabled(editable)
        self._dtr_check.setEnabled(editable)
        self._rts_check.setEnabled(editable)
        self._refresh_btn.setEnabled(editable)
        self._tx_input.set_send_enabled(connected)
        self._clear_btn.setEnabled(True)
        self._connect_btn.setEnabled(not busy)
        self._connect_action.setEnabled(not busy)
        label = "Disconnect" if connected else "Connect"
        self._connect_btn.setText(label)
        self._connect_action.setText(label)
        # Dot state is driven by _on_connection via engine state; keep button property in sync
        self._connect_btn.setProperty("connected", connected)
        self._connect_btn.style().unpolish(self._connect_btn)
        self._connect_btn.style().polish(self._connect_btn)

    def _send_input(self, text: str | None = None) -> None:
        """Send a message typed in the TX input (Send button or Enter)."""
        if text is None:
            text = self._tx_input.text()
        self._send_text(text, record=True, clear_input=True)

    def _send_resend(self, text: str) -> None:
        """Re-send the previous command without disturbing the current input."""
        self._send_text(text, record=False, clear_input=False, bypass_duplicate=True)

    def _send_text(
        self,
        text: str,
        *,
        record: bool = True,
        clear_input: bool = False,
        bypass_duplicate: bool = False,
    ) -> None:
        """Write *text* to the port, applying the configured line ending.

        Guards against accidental duplicate sends: a second, identical command
        within a short debounce window is ignored.  Empty text is never sent.
        """
        text = text.strip()
        if not text:
            return
        command = parse_line_control_command(text)
        if command is not None:
            logger.debug("Line-control command: %r", text)
            self._apply_line_control(command)
            return
        if not self._bridge.is_connected:
            self._on_error("Not connected — can't send.")
            return
        if not bypass_duplicate and self._is_duplicate_send(text):
            logger.debug("Skipping duplicate TX: %r", text)
            return
        payload = text.encode("utf-8")
        ending = self._terminal.model.line_ending_bytes()
        self._bridge.write(payload + ending)
        self._state.sent_bytes += len(payload) + len(ending)
        self._last_sent_text = text
        self._last_sent_time = time.monotonic()
        self._activity.tx_activity()
        self._terminal.append_tx(text)
        if record:
            self._tx_input.remember(text)
        if clear_input:
            self._tx_input.clear_input()
        self._refresh_counters()

    def _is_duplicate_send(self, text: str) -> bool:
        """Return whether *text* is an identical command sent moments ago."""
        now = time.monotonic()
        return (
            self._last_sent_text == text
            and (now - self._last_sent_time) < (self._duplicate_debounce_ms / 1000.0)
        )

    def _send_quick_command(self, command: str) -> None:
        """Transmit a preset command (from the quick-commands list)."""
        self._send_text(command, record=True, clear_input=False)

    def _select_parser(self, name: str) -> None:
        """Switch the active protocol parser, discarding any buffered state."""
        self._parser = registry.create(name)
        self._state.parser = name
        if not self._loading:
            self._config.parser = name
            self._persist()
        logger.debug("Parser set to %r", name)

    def _on_port_changed(self, *args: object) -> None:
        """Persist the port selection when the user changes it."""
        if self._loading:
            return
        cfg = self._config.serial
        if self._port_combo.currentData() is not None:
            cfg.port = self._port_combo.currentData()
        self._persist()

    def _on_baud_changed(self, *args: object) -> None:
        """Persist the baud selection when the user changes it (keeping the port)."""
        if self._loading:
            return
        try:
            self._config.serial.baudrate = int(self._baud_combo.currentText())
        except ValueError:
            return
        self._persist()

    # -- Line control ---------------------------------------------------------

    def _on_dtr_toggled(self, enabled: bool) -> None:
        """Persist and apply a change to the DTR toggle."""
        if self._loading:
            return
        self._apply_line_level("dtr", enabled)

    def _on_rts_toggled(self, enabled: bool) -> None:
        """Persist and apply a change to the RTS toggle."""
        if self._loading:
            return
        self._apply_line_level("rts", enabled)

    def _apply_line_level(self, line: str, enabled: bool) -> None:
        """Persist a DTR/RTS level and apply it live while connected."""
        if line == "dtr":
            self._config.serial.dtr = enabled
            self._bridge.set_dtr(enabled)
        else:
            self._config.serial.rts = enabled
            self._bridge.set_rts(enabled)
        self._persist()
        self._refresh_line_state()

    def _apply_line_control(self, command: LineControlCommand) -> None:
        """Apply a typed ``DTR|RTS ON|OFF`` command without transmitting data."""
        self._apply_line_level(command.line, command.enabled)
        check = self._dtr_check if command.line == "dtr" else self._rts_check
        check.blockSignals(True)
        check.setChecked(command.enabled)
        check.blockSignals(False)

    def _on_reconnect_enabled_toggled(self, enabled: bool) -> None:
        """Persist and apply a change to the auto-reconnect toggle."""
        if self._loading:
            return
        self._config.reconnect_enabled = enabled
        self._persist()
        self._bridge.set_reconnect_enabled(enabled)

    def _on_reconnect_interval_changed(self, value: float) -> None:
        """Persist and apply a change to the reconnect retry interval."""
        if self._loading:
            return
        self._config.reconnect_interval = float(value)
        self._persist()
        self._bridge.set_reconnect_interval(float(value))

    def _refresh_line_state(self) -> None:
        """Refresh the status-bar label to match the engine's live line state."""
        state = self._bridge.line_state()
        dtr = state.dtr if state.dtr is not None else self._dtr_check.isChecked()
        rts = state.rts if state.rts is not None else self._rts_check.isChecked()
        self._line_state_label.setText(
            f"DTR: {_fmt_onoff(dtr)}   RTS: {_fmt_onoff(rts)}"
        )

    # -- Signal handlers ------------------------------------------------------

    def _on_data(self, data: bytes) -> None:
        self._state.received_bytes += len(data)
        if self._parser is not None:
            events = self._parser.feed(data)
            if events:
                self._terminal.append_events(events)
        self._activity.rx_activity()
        self._refresh_counters()

    def _update_options(self) -> None:
        """Push the widget state into the shared terminal view-model options."""
        options = self._terminal.model.options
        options.show_timestamp = self._timestamp_check.isChecked()
        options.autoscroll = self._autoscroll_check.isChecked()
        options.clear_on_connect = self._clear_on_connect_check.isChecked()
        options.show_flow_markers = self._flow_markers_check.isChecked()
        options.show_eof_marker = self._eof_check.isChecked()
        options.line_ending = self._line_ending_combo.currentText()
        options.word_wrap = self._wrap_check.isChecked()

    def _on_max_lines_changed(self) -> None:
        """Apply the selected scrollback limit to the terminal."""
        self._terminal.set_scrollback_limit(int(self._max_lines_combo.currentData()))

    def _refresh_counters(self) -> None:
        """Update the status-bar byte counter from the shared app state."""
        self._byte_counter.set_counts(self._state.received_bytes, self._state.sent_bytes)

    def _on_connection(self, state: ConnectionState, message: str) -> None:
        self._state.connection_state = state
        is_connected = state is ConnectionState.CONNECTED
        if is_connected:
            self._terminal.on_connect()
        elif state in (ConnectionState.DISCONNECTED, ConnectionState.ERROR):
            if self._parser is not None:
                self._parser.reset()
            self._terminal.on_disconnect()
        self._status_label.setText(message)
        if is_connected:
            dot = "connected"
        elif state in (ConnectionState.CONNECTING, ConnectionState.RECONNECTING, ConnectionState.DISCONNECTING):
            dot = "busy"
        elif state is ConnectionState.ERROR:
            dot = "error"
        else:
            dot = "disconnected"
        self._status_dot.set_state(dot)
        self._update_controls()
        self._refresh_line_state()
        logger.info("Connection state: %s", message)

    def _on_error(self, message: str) -> None:
        self._state.last_error = message
        self._status_label.setText(message)
        self._status_dot.set_state("error")
        self._update_controls()
        logger.error("UI error: %s", message)
        self._show_error_dialog(message)

    def _show_error_dialog(self, message: str) -> None:
        """Present a modal warning so the user notices the failure."""
        QMessageBox.warning(self, "Serial Monitor", message)

    # -- Window lifecycle -----------------------------------------------------

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._save_geometry()

    def moveEvent(self, event) -> None:
        super().moveEvent(event)
        self._save_geometry()

    def closeEvent(self, event) -> None:
        self._bridge.stop_auto_refresh()
        self._save_geometry()
        super().closeEvent(event)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._bridge.start_auto_refresh()
        if self._config.window.maximized and not self._maximized_applied:
            self._maximized_applied = True
            self.showMaximized()
