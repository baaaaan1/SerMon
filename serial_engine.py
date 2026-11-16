"""Qt-core serial engine (no widgets).

``SerialManager`` owns the lifecycle of a pyserial connection and a background
reader thread, and exposes a small observer API via Qt signals.  A GUI layer
can attach to ``data_received`` / ``connected`` / ``disconnected`` /
``status_changed`` without touching pyserial directly.

It is deliberately GUI-agnostic: only ``PySide6.QtCore.QObject``/``Signal`` are
used so the signals are marshalled on to the GUI (main) thread automatically.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, replace

from PySide6.QtCore import QObject, Signal

import serial
import serial.tools.list_ports as _list_ports


# --------------------------------------------------------------------------- #
#  Public helpers
# --------------------------------------------------------------------------- #
@dataclass
class PortInfo:
    """Lightweight description of a detected serial port."""
    device: str
    description: str

    def __str__(self) -> str:  # used in the combo box
        return self.device


def available_ports() -> list[PortInfo]:
    """Return the currently detected ports."""
    raw = _list_ports.comports()
    return [PortInfo(p.device, p.description) for p in raw]


@dataclass
class SerialConfig:
    """Connection parameters used to open the port."""
    port: str = ""
    baudrate: int = 115200
    timeout: float = 0.05
    write_timeout: float = 2.0


# --------------------------------------------------------------------------- #
#  Engine
# --------------------------------------------------------------------------- #
class SerialManager(QObject):
    """Threaded serial connection with optional auto-reconnect.

    Signals
    -------
    data_received(bytes)    raw chunk read from the port
    connected(str)          port name once (re)connected
    disconnected(str)       reason why the link went away
    status_changed(str)     human friendly status message
    event_received(int, str, object) request-tagged notifications for GUI delivery
    """

    data_received = Signal(bytes)
    connected     = Signal(str)
    disconnected  = Signal(str)
    status_changed = Signal(str)
    event_received = Signal(int, str, object)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._cfg = SerialConfig()
        self._ser: serial.Serial | None = None
        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

        # A failed request can be resumed by enabling retries, but a canceled
        # request (or a fresh launch) must never connect on its own.
        self._connection_intent = False
        self._want_connected = False
        self._generation = 0
        self._request_id = 0
        self._retrying = False
        self._retry_at = 0.0
        self._auto_reconnect = False
        self._reconnect_delay = 1.0
        self._dtr = True
        self._rx = 0
        self._tx = 0

    # -- read-only state --------------------------------------------------- #
    @property
    def is_open(self) -> bool:
        with self._lock:
            s = self._ser
            return s is not None and s.is_open

    @property
    def connection_requested(self) -> bool:
        """Whether connected, connecting, or actively waiting for a retry."""
        with self._lock:
            return self._want_connected

    @property
    def request_id(self) -> int:
        """User request identity, retained across automatic loss and retries."""
        with self._lock:
            return self._request_id

    @property
    def port(self) -> str:
        """The live connection's port, or the configured port while closed."""
        with self._lock:
            return self._ser.port if self._ser is not None else self._cfg.port

    @property
    def baudrate(self) -> int:
        """The live connection's baud rate, or the configured rate while closed."""
        with self._lock:
            return self._ser.baudrate if self._ser is not None else self._cfg.baudrate

    @property
    def dtr(self) -> bool:
        with self._lock:
            return self._dtr

    @property
    def rx_count(self) -> int:
        with self._lock:
            return self._rx

    @property
    def tx_count(self) -> int:
        with self._lock:
            return self._tx

    @property
    def auto_reconnect(self) -> bool:
        with self._lock:
            return self._auto_reconnect

    # -- configuration ----------------------------------------------------- #
    def configure(self, port: str, baudrate: int) -> None:
        with self._lock:
            self._cfg.port = port
            self._cfg.baudrate = baudrate

    def set_auto_reconnect(self, enabled: bool) -> None:
        with self._condition:
            self._auto_reconnect = bool(enabled)
            if enabled and self._connection_intent and not self._want_connected:
                self._want_connected = True
                self._generation += 1
                self._request_id += 1
                self._retrying = True
                self._retry_at = 0.0
                self._start_worker()
            elif not enabled and self._ser is None and self._retrying:
                self._want_connected = False
                self._generation += 1
                self._request_id += 1
                self._retry_at = 0.0
            self._condition.notify_all()
            self._emit_event(
                "status_changed",
                "Auto-reconnect enabled" if enabled else "Auto-reconnect disabled"
            )

    def set_dtr(self, value: bool) -> None:
        """Set/clear DTR.  Applied immediately if the port is open."""
        with self._lock:
            self._dtr = bool(value)
            if self._ser is not None and self._ser.is_open:
                try:
                    self._ser.dtr = self._dtr
                except Exception as e:   # noqa: BLE001
                    self._emit_event("status_changed", f"DTR error: {e}")

    # -- connection control ------------------------------------------------ #
    def connect(self, port: str | None = None, baudrate: int | None = None) -> None:
        with self._condition:
            if port is not None:
                self._cfg.port = port
            if baudrate is not None:
                self._cfg.baudrate = baudrate
            if self.is_open:
                self._emit_event("status_changed", "Already connected")
                return
            self._close_port()
            self._connection_intent = True
            self._want_connected = True
            self._generation += 1
            self._request_id += 1
            self._retrying = False
            self._retry_at = 0.0
            self._start_worker()
            self._condition.notify_all()
            self._emit_event("status_changed", "Connecting...")

    def disconnect(self) -> None:
        with self._condition:
            self._connection_intent = False
            self._want_connected = False
            self._generation += 1
            self._request_id += 1
            generation = self._generation
            self._retrying = False
            self._retry_at = 0.0
            self._close_port()
            self._condition.notify_all()
            self._emit_event("disconnected", "user")
            if generation == self._generation:
                self._emit_event("status_changed", "Disconnected")

    def stop(self) -> None:
        """Shutdown: stop the worker thread and release the port."""
        with self._condition:
            self._connection_intent = False
            self._want_connected = False
            self._generation += 1
            self._request_id += 1
            self._retrying = False
            self._retry_at = 0.0
            self._stop.set()
            self._close_port()
            self._condition.notify_all()
            thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=2.0)

    def write(self, data: bytes) -> int:
        """Write bytes to the port; returns bytes written or -1 on failure."""
        with self._condition:
            s = self._ser
            if s is None:
                return -1
            try:
                if not s.is_open:
                    raise serial.SerialException("port closed")
                n = s.write(data)
                self._tx += n
                return n
            except Exception as e:   # noqa: BLE001
                self._connection_lost(s, self._generation, f"TX error: {e}")
                return -1

    # -- internals --------------------------------------------------------- #
    def _emit_event(self, kind: str, payload) -> None:
        # Qt cannot retract queued signals after cancellation. The GUI filters
        # superseded requests, without dropping RX queued before a natural loss.
        self.event_received.emit(self._request_id, kind, payload)
        getattr(self, kind).emit(payload)

    def _start_worker(self) -> None:
        """Called with the condition held; an idle worker is kept until stop."""
        self._stop.clear()
        if self._thread is None:
            self._thread = threading.Thread(
                target=self._run, name="serial-engine", daemon=True
            )
            self._thread.start()

    def _request_current(self, generation: int) -> bool:
        return (
            generation == self._generation
            and self._want_connected
            and not self._stop.is_set()
        )

    def _open_port(self, generation: int, cfg: SerialConfig) -> None:
        s = None
        try:
            # Retain the object before open(), including partially opened handles
            # on failure. Never publish a handle until DTR setup also succeeds.
            s = serial.Serial(
                port=None,
                baudrate=cfg.baudrate,
                timeout=cfg.timeout,
                write_timeout=cfg.write_timeout,
            )
            s.port = cfg.port
            with self._condition:
                if not self._request_current(generation):
                    return
            s.open()
            while True:
                with self._condition:
                    if not self._request_current(generation):
                        return
                    dtr = self._dtr
                s.dtr = dtr
                with self._condition:
                    if not self._request_current(generation):
                        return
                    if dtr != self._dtr:
                        continue
                    self._ser = s
                    s = None  # Ownership transfers to the manager.
                    self._retrying = False
                    self._retry_at = 0.0
                    self._rx = 0
                    self._tx = 0
                    self._emit_event("connected", cfg.port)
                    return
        except Exception as e:   # noqa: BLE001
            self._close_handle(s)
            s = None
            with self._condition:
                if not self._request_current(generation):
                    return
                self._retrying = True
                self._want_connected = self._auto_reconnect
                self._retry_at = time.monotonic() + self._reconnect_delay
                self._emit_event("status_changed", f"Open {cfg.port}: {e}")
                if generation == self._generation:
                    self._emit_event(
                        "status_changed",
                        f"Retrying in {self._reconnect_delay:.0f}s..."
                        if self._want_connected else "Connection failed"
                    )
                self._condition.notify_all()
        finally:
            self._close_handle(s)

    @staticmethod
    def _close_handle(s: serial.Serial | None) -> None:
        if s is not None:
            try:
                s.close()
            except Exception:   # noqa: BLE001
                pass

    def _close_port(self) -> None:
        s, self._ser = self._ser, None
        self._close_handle(s)

    def _connection_lost(self, s: serial.Serial, generation: int, reason: str) -> None:
        """Retire only the current handle; read and TX failures share this path."""
        if not self._request_current(generation) or self._ser is not s:
            return
        self._generation += 1
        generation = self._generation
        self._retrying = True
        self._want_connected = self._auto_reconnect
        self._retry_at = time.monotonic() + self._reconnect_delay
        self._close_port()
        self._emit_event("disconnected", reason)
        if generation == self._generation:
            self._emit_event(
                "status_changed",
                f"Link lost ({reason}) - auto-reconnecting..."
                if self._want_connected else f"Disconnected: {reason}"
            )
        self._condition.notify_all()

    def _run(self) -> None:
        """Wait for requests, open privately, and read a stable handle snapshot."""
        while True:
            with self._condition:
                while True:
                    if self._stop.is_set():
                        self._thread = None
                        return
                    if not self._want_connected:
                        self._condition.wait()
                        continue
                    remaining = self._retry_at - time.monotonic()
                    if self._ser is None and remaining > 0:
                        self._condition.wait(remaining)
                        continue
                    s = self._ser
                    generation = self._generation
                    cfg = replace(self._cfg)
                    break
            if s is None:
                self._open_port(generation, cfg)
                continue

            try:
                if not s.is_open:
                    raise serial.SerialException("port closed")
                waiting = s.in_waiting
                data = s.read(waiting) if waiting else b""
            except Exception as e:   # noqa: BLE001 - link went away
                with self._condition:
                    self._connection_lost(s, generation, str(e) or "connection lost")
            else:
                with self._condition:
                    # close() may interrupt a read. Its result belongs only to
                    # this handle and request, never a subsequent connection.
                    if not self._request_current(generation) or self._ser is not s:
                        continue
                    if data:
                        self._rx += len(data)
                        self._emit_event("data_received", data)
                    else:
                        self._condition.wait(0.02)


