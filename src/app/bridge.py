"""Qt bridge between the serial engine and the UI.

This is the *only* module allowed to know about both PySide6 and the serial
engine.  It adapts the engine's plain-Python callbacks into Qt signals so that
widgets can subscribe safely from the main thread, while the engine itself stays
Qt-free.
"""

from __future__ import annotations

import logging
import threading

from PySide6.QtCore import QObject, QTimer, Signal

from serial_engine.manager import ConnectionState, SerialManager, SerialManagerProtocol
from serial_engine.port_scanner import PortInfo
from serial_engine.session import LineState

logger = logging.getLogger(__name__)


class SerialBridge(QObject):
    """Expose :class:`SerialManager` events as Qt signals.

    Signals
    -------
    data_received(bytes)
        Emitted for each chunk of raw bytes arriving from the port.
    connection_changed(ConnectionState, str)
        Emitted when the connection state changes; payload is
        ``(state, message)``.
    error_occurred(str)
        Emitted when an error occurs; payload is a human-readable message.
    ports_refreshed(list)
        Emitted whenever the set of available serial ports changes; the payload
        is ``list[PortInfo]`` sorted by device.
    """

    data_received = Signal(bytes)
    connection_changed = Signal(object, str)
    error_occurred = Signal(str)
    ports_refreshed = Signal(list)

    def __init__(
        self,
        manager: SerialManagerProtocol | None = None,
        *,
        auto_refresh_ms: int = 1000,
        flush_interval_ms: int = 30,
        max_rx_buffer: int = 262144,
        reconnect_enabled: bool = True,
        reconnect_interval: float = 1.0,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._manager = manager or SerialManager(
            reconnect_enabled=reconnect_enabled,
            reconnect_interval=reconnect_interval,
        )
        #: Last snapshot of ports, used to detect changes before emitting.
        self._last_ports: list[PortInfo] = []
        #: Polling timer so plug/unplug is detected without any OS hotplug API
        #: or chipset/MCU-specific assumptions.
        self._timer = QTimer(self)
        self._timer.setInterval(auto_refresh_ms)
        self._timer.timeout.connect(self._poll_ports)
        # --- RX coalescing ---------------------------------------------------
        #: Backing buffer for bytes waiting to be delivered to the UI.  Coalescing
        #: bounds the rate of ``data_received`` signals regardless of how fast the
        #: device streams, so the main thread is never flooded under high RX
        #: traffic (keeps the UI responsive without dropping binary data).
        self._rx_buffer = bytearray()
        self._max_rx_buffer = max(1, max_rx_buffer)
        self._rx_lock = threading.Lock()
        #: Flushes the coalesced RX buffer on the main thread at a fixed rate.
        self._flush_timer = QTimer(self)
        self._flush_timer.setInterval(flush_interval_ms)
        self._flush_timer.timeout.connect(self._flush_rx)
        self._flush_timer.start()
        # Engine callbacks are invoked on the reader thread; they only append to
        # the RX buffer (cheap, non-blocking).  Delivery to the UI happens on the
        # main thread via ``_flush_rx``, so downstream slots always run on the
        # correct thread and at a bounded signal rate.
        self._manager.subscribe_data(self._on_data)
        self._manager.subscribe_status(self._on_status)
        self._manager.subscribe_error(self._on_error)

    @property
    def manager(self) -> SerialManagerProtocol:
        """The underlying Qt-free engine."""
        return self._manager

    @property
    def is_connected(self) -> bool:
        """Whether the engine currently has a live connection."""
        return self._manager.is_connected

    @property
    def connection_state(self) -> ConnectionState:
        """Current connection state from the engine."""
        return self._manager.state

    def set_reconnect_enabled(self, enabled: bool) -> None:
        """Enable/disable automatic reconnection after an unexpected disconnect."""
        self._manager.set_reconnect_enabled(enabled)

    @property
    def reconnect_enabled(self) -> bool:
        """Whether automatic reconnection is currently enabled."""
        return self._manager.reconnect_enabled

    def set_reconnect_interval(self, interval: float) -> None:
        """Set the retry interval (seconds) used while waiting for a device."""
        self._manager.set_reconnect_interval(interval)

    @property
    def reconnect_interval(self) -> float:
        """Retry interval (seconds) used while waiting for a device."""
        return self._manager.reconnect_interval

    def connect_port(self, port: str, baudrate: int = 9600, **kwargs: object) -> None:
        """Open a serial connection, translating errors into a signal."""
        try:
            self._manager.open_connection(port, baudrate=baudrate, **kwargs)
        except Exception as exc:
            logger.exception("Failed to connect to %s", port)
            self.error_occurred.emit(str(exc))

    def disconnect_port(self) -> None:
        """Close the current serial connection."""
        try:
            self._manager.close_connection()
        except Exception as exc:
            logger.exception("Failed to disconnect")
            self.error_occurred.emit(str(exc))

    def write(self, data: bytes) -> None:
        """Write *data* to the port, translating errors into a signal."""
        try:
            self._manager.write(data)
        except Exception as exc:
            logger.exception("Failed to write to serial port")
            self.error_occurred.emit(str(exc))

    def set_dtr(self, enabled: bool) -> None:
        """Set the DTR line level, translating errors into a signal."""
        try:
            self._manager.set_dtr(enabled)
        except Exception as exc:
            logger.exception("Failed to set DTR")
            self.error_occurred.emit(str(exc))

    def set_rts(self, enabled: bool) -> None:
        """Set the RTS line level, translating errors into a signal."""
        try:
            self._manager.set_rts(enabled)
        except Exception as exc:
            logger.exception("Failed to set RTS")
            self.error_occurred.emit(str(exc))

    def get_dtr(self) -> bool | None:
        """Return the current desired DTR level."""
        return self._manager.get_dtr()

    def get_rts(self) -> bool | None:
        """Return the current desired RTS level."""
        return self._manager.get_rts()

    def line_state(self) -> LineState:
        """Return a snapshot of the DTR/RTS line levels."""
        return self._manager.line_state()

    def get_ports(self) -> list[PortInfo]:
        """Enumerate available serial ports (a one-shot read, no change tracking)."""
        return self._manager.list_ports()

    def refresh_ports(self) -> None:
        """Scan for ports now and emit ``ports_refreshed`` when they change.

        This is shared by the manual "Refresh" button and the automatic polling
        timer, so both paths use the same change detection.
        """
        self._poll_ports()

    def start_auto_refresh(self, interval_ms: int | None = None) -> None:
        """Begin periodically scanning for port changes (idempotent)."""
        if interval_ms is not None and interval_ms > 0:
            self._timer.setInterval(interval_ms)
        if not self._timer.isActive():
            self._timer.start()

    def stop_auto_refresh(self) -> None:
        """Stop periodically scanning for port changes."""
        self._timer.stop()

    def _poll_ports(self) -> None:
        """Compare a fresh scan with the last snapshot; signal on any change."""
        try:
            ports = self._manager.list_ports()
        except Exception:
            logger.exception("Failed to enumerate serial ports")
            return
        if ports != self._last_ports:
            self._last_ports = ports
            self.ports_refreshed.emit(list(ports))

    # -- Engine callbacks (invoked on the reader thread) -------------------

    def _on_data(self, data: bytes) -> None:
        """Buffer incoming bytes (reader thread) instead of signalling per chunk.

        The reader thread only appends to a buffer, so it never floods the UI
        event queue.  The flush timer (main thread) later emits one aggregated
        ``data_received`` signal per tick.  If the buffer overfills before a tick
        we flush immediately to bound memory growth without dropping data.
        """
        if not data:
            return
        with self._rx_lock:
            self._rx_buffer.extend(data)
            overflow = len(self._rx_buffer) >= self._max_rx_buffer
        if overflow:
            logger.warning("RX buffer hit %d bytes; flushing early", self._max_rx_buffer)
            self._flush_rx()

    def _flush_rx(self) -> None:
        """Deliver the coalesced RX buffer as a single ``data_received`` signal.

        Runs on the main thread (via the flush timer) or when the buffer
        overflows.  Emitting here means every connected slot executes on the main
        thread with a bounded rate, preserving binary data exactly.
        """
        with self._rx_lock:
            if not self._rx_buffer:
                return
            data = bytes(self._rx_buffer)
            self._rx_buffer.clear()
        self.data_received.emit(data)

    def _on_status(self, state: ConnectionState, message: str) -> None:
        self.connection_changed.emit(state, message)

    def _on_error(self, exc: Exception) -> None:
        self.error_occurred.emit(str(exc))
