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
from dataclasses import dataclass

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
    """

    data_received = Signal(bytes)
    connected     = Signal(str)
    disconnected  = Signal(str)
    status_changed = Signal(str)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._cfg = SerialConfig()
        self._ser: serial.Serial | None = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

        self._want_connected = False
        self._auto_reconnect = False
        self._reconnect_delay = 1.0
        self._dtr = True
        self._rx = 0
        self._tx = 0

    # -- read-only state --------------------------------------------------- #
    @property
    def is_open(self) -> bool:
        s = self._ser
        return s is not None and s.is_open

    @property
    def dtr(self) -> bool:
        return self._dtr

    @property
    def rx_count(self) -> int:
        return self._rx

    @property
    def tx_count(self) -> int:
        return self._tx

    @property
    def auto_reconnect(self) -> bool:
        return self._auto_reconnect
    # -- configuration ----------------------------------------------------- #
    def configure(self, port: str, baudrate: int) -> None:
        self._cfg.port = port
        self._cfg.baudrate = baudrate

    def set_auto_reconnect(self, enabled: bool) -> None:
        self._auto_reconnect = bool(enabled)
        if enabled:
            self.status_changed.emit("Auto-reconnect enabled")

    def set_dtr(self, value: bool) -> None:
        """Set/clear DTR.  Applied immediately if the port is open."""
        self._dtr = bool(value)
        with self._lock:
            if self._ser is not None and self._ser.is_open:
                try:
                    self._ser.dtr = self._dtr
                except Exception as e:   # noqa: BLE001
                    self.status_changed.emit(f"DTR error: {e}")

    # -- connection control ------------------------------------------------ #
    def connect(self, port: str | None = None, baudrate: int | None = None) -> None:
        if port:
            self._cfg.port = port
        if baudrate:
            self._cfg.baudrate = baudrate
        if self.is_open:
            self.status_changed.emit("Already connected")
            return
        self._want_connected = True
        if self._thread is None or not self._thread.is_alive():
            self._stop = threading.Event()
            self._thread = threading.Thread(
                target=self._run, name="serial-engine", daemon=True
            )
            self._thread.start()
        else:
            self.status_changed.emit("Connecting...")

    def disconnect(self) -> None:
        self._want_connected = False
        self._close_port()
        self.disconnected.emit("user")
        self.status_changed.emit("Disconnected")

    def stop(self) -> None:
        """Shutdown: stop the worker thread and release the port."""
        self._want_connected = False
        self._stop.set()
        self._close_port()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)
        self._thread = None

    def write(self, data: bytes) -> int:
        """Write bytes to the port; returns bytes written or -1 on failure."""
        with self._lock:
            if self._ser is None or not self._ser.is_open:
                return -1
            try:
                n = self._ser.write(data)
                self._tx += n
                return n
            except Exception as e:   # noqa: BLE001
                self.status_changed.emit(f"TX error: {e}")
                return -1
    # -- internals --------------------------------------------------------- #
    def _open_port(self) -> bool:
        with self._lock:
            if self._ser is not None:
                return self._ser.is_open
            try:
                self._ser = serial.Serial(
                    port=self._cfg.port,
                    baudrate=self._cfg.baudrate,
                    timeout=self._cfg.timeout,
                    write_timeout=self._cfg.write_timeout,
                )
                self._ser.dtr = self._dtr
                return True
            except Exception as e:   # noqa: BLE001
                self._ser = None
                self.status_changed.emit(f"Open {self._cfg.port}: {e}")
                return False

    def _close_port(self) -> None:
        with self._lock:
            if self._ser is not None:
                try:
                    self._ser.close()
                except Exception:   # noqa: BLE001
                    pass
                self._ser = None

    def _run(self) -> None:
        """Worker loop: (re)connect, read, auto-reconnect on failure."""
        while not self._stop.is_set():
            if not self._want_connected:
                if self._stop.wait(0.05):
                    break
                continue

            # -- connect stage ------------------------------------------- #
            if self._ser is None:
                if not self._open_port():
                    if self._auto_reconnect:
                        self.status_changed.emit(
                            f"Retrying in {self._reconnect_delay:.0f}s..."
                        )
                        if self._stop.wait(self._reconnect_delay):
                            break
                    else:
                        self._want_connected = False
                        self.status_changed.emit("Connection failed")
                    continue
                self._rx = 0
                self._tx = 0
                self.connected.emit(self._cfg.port)

            # -- read stage ---------------------------------------------- #
            try:
                if not self._ser.is_open:
                    raise serial.SerialException("port closed")
                waiting = self._ser.in_waiting
                if waiting:
                    data = self._ser.read(waiting)
                    if data:
                        self._rx += len(data)
                        self.data_received.emit(data)
                else:
                    if self._stop.wait(0.02):
                        break
                if not self._want_connected:
                    self._close_port()
                    break
            except Exception as e:   # noqa: BLE001 - link went away
                self._close_port()
                self.disconnected.emit(str(e) or "connection lost")
                if self._auto_reconnect:
                    self.status_changed.emit("Link lost - auto-reconnecting...")
                    if self._stop.wait(self._reconnect_delay):
                        break
                else:
                    self._want_connected = False
                    self.status_changed.emit(f"Disconnected: {e}")
                continue

        self._close_port()


