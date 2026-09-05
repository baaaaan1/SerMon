"""Qt-free serial engine facade.

The :class:`SerialManager` owns the lifecycle of a serial connection and its
reader thread, and exposes a small observer API.  Any front-end (Qt GUI or CLI)
can attach data/status/error callbacks without ever touching pyserial.
"""

from __future__ import annotations

import enum
import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from services.reconnect import ReconnectPolicy

from .exceptions import SerialMonitorError, SerialPortNotFoundError
from .port_scanner import PortInfo, list_serial_ports
from .session import LineState, SerialSession
from .worker import SerialReaderWorker

logger = logging.getLogger(__name__)

#: Receives a chunk of raw bytes from the reader thread.
DataCallback = Callable[[bytes], None]
#: Receives ``(state, message)`` when the connection state changes.
StatusCallback = Callable[["ConnectionState", str], None]
#: Receives an exception when something goes wrong.
ErrorCallback = Callable[[Exception], None]


class ConnectionState(str, enum.Enum):
    """Explicit connection lifecycle owned by the engine."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    DISCONNECTING = "disconnecting"
    RECONNECTING = "reconnecting"
    ERROR = "error"

    @property
    def is_connected(self) -> bool:
        return self is ConnectionState.CONNECTED

    @property
    def is_busy(self) -> bool:
        return self in (
            ConnectionState.CONNECTING,
            ConnectionState.DISCONNECTING,
            ConnectionState.RECONNECTING,
        )

    @property
    def is_editable(self) -> bool:
        return self in (ConnectionState.DISCONNECTED, ConnectionState.ERROR)


_ALLOWED_TRANSITIONS: dict[ConnectionState, set[ConnectionState]] = {
    ConnectionState.DISCONNECTED: {ConnectionState.CONNECTING},
    ConnectionState.CONNECTING: {
        ConnectionState.CONNECTED,
        ConnectionState.ERROR,
        ConnectionState.DISCONNECTED,
    },
    ConnectionState.CONNECTED: {ConnectionState.DISCONNECTING, ConnectionState.ERROR},
    ConnectionState.DISCONNECTING: {ConnectionState.DISCONNECTED, ConnectionState.ERROR},
    ConnectionState.ERROR: {
        ConnectionState.CONNECTING,
        ConnectionState.DISCONNECTING,
        ConnectionState.RECONNECTING,
        ConnectionState.DISCONNECTED,
    },
    ConnectionState.RECONNECTING: {
        ConnectionState.CONNECTED,
        ConnectionState.ERROR,
        ConnectionState.DISCONNECTING,
        ConnectionState.DISCONNECTED,
    },
}


class SerialManagerProtocol(Protocol):
    """Structural interface for the manager a front-end (e.g. the Qt bridge) consumes.

    Concrete implementations (:class:`SerialManager`) are duck-typed against this
    protocol -- it is *not* a base class.  Decoupling the bridge from the concrete
    manager lets tests inject lightweight fakes that satisfy the same shape without
    subclassing or importing the real, thread-spawning manager.
    """

    @property
    def state(self) -> ConnectionState: ...

    @property
    def is_connected(self) -> bool: ...

    def subscribe_data(self, callback: DataCallback) -> None: ...
    def subscribe_status(self, callback: StatusCallback) -> None: ...
    def subscribe_error(self, callback: ErrorCallback) -> None: ...
    def open_connection(self, port: str, baudrate: int = 9600, **kwargs: object) -> None: ...
    def close_connection(self) -> None: ...
    def write(self, data: bytes) -> int: ...
    def list_ports(self) -> list[PortInfo]: ...
    def set_dtr(self, enabled: bool) -> None: ...
    def set_rts(self, enabled: bool) -> None: ...
    def get_dtr(self) -> bool | None: ...
    def get_rts(self) -> bool | None: ...
    def line_state(self) -> LineState: ...

    @property
    def reconnect_enabled(self) -> bool: ...
    @property
    def reconnect_interval(self) -> float: ...
    def set_reconnect_enabled(self, enabled: bool) -> None: ...
    def set_reconnect_interval(self, interval: float) -> None: ...


@dataclass(frozen=True)
class ConnectionStatus:
    """A snapshot of the current connection state."""

    state: ConnectionState
    message: str = ""

    @property
    def connected(self) -> bool:
        return self.state is ConnectionState.CONNECTED

    def __init__(self, state: ConnectionState | bool, message: str = "") -> None:
        if isinstance(state, bool):
            cs = ConnectionState.CONNECTED if state else ConnectionState.DISCONNECTED
            object.__setattr__(self, "state", cs)
        else:
            object.__setattr__(self, "state", state)
        object.__setattr__(self, "message", message)


class SerialManager:
    """Coordinate a serial session and its reader thread.

    The manager never imports Qt.  Subscribers are plain callables invoked from
    the reader thread; the front-end is responsible for marshalling those calls
    onto its own event loop (e.g. by emitting Qt signals from the bridge).
    """

    def __init__(
        self,
        *,
        buffer_size: int = 4096,
        poll_interval: float = 0.01,
        reconnect_enabled: bool = True,
        reconnect_policy: ReconnectPolicy | None = None,
        reconnect_interval: float = 1.0,
        port_presence_check: Callable[[str], bool] | None = None,
    ) -> None:
        self._buffer_size = buffer_size
        self._poll_interval = poll_interval
        self._session: SerialSession | None = None
        self._worker: SerialReaderWorker | None = None
        self._lock = threading.RLock()
        self._state: ConnectionState = ConnectionState.DISCONNECTED
        self._status_message = "Disconnected"
        #: Desired DTR/RTS line levels (``None`` = leave at the driver default).
        self._dtr: bool | None = None
        self._rts: bool | None = None

        self._data_subscribers: list[DataCallback] = []
        self._status_subscribers: list[StatusCallback] = []
        self._error_subscribers: list[ErrorCallback] = []

        # Reconnection policy: retry an unexpected disconnect with backoff.
        self._reconnect_enabled = reconnect_enabled
        self._reconnect_policy = reconnect_policy or ReconnectPolicy()
        #: How often (seconds) to poll for the device while reconnecting.
        self._reconnect_interval = max(0.0, float(reconnect_interval))
        #: Device-presence oracle; defaults to enumerating the OS port list.
        self._port_presence_check = port_presence_check or self._default_port_presence_check
        self._reconnect_thread: threading.Thread | None = None
        self._reconnect_stop_event: threading.Event | None = None
        self._last_open: tuple[str, int, dict[str, object]] | None = None

    # -- Observer API -----------------------------------------------------

    def subscribe_data(self, callback: DataCallback) -> None:
        """Subscribe to raw chunks of incoming bytes."""
        self._data_subscribers.append(callback)

    def subscribe_status(self, callback: StatusCallback) -> None:
        """Subscribe to ``(connected, message)`` state changes."""
        self._status_subscribers.append(callback)

    def subscribe_error(self, callback: ErrorCallback) -> None:
        """Subscribe to asynchronous errors from the reader thread."""
        self._error_subscribers.append(callback)

    def unsubscribe(self, callback: Callable) -> None:
        """Remove *callback* from every subscriber list."""
        for attr in ("_data_subscribers", "_status_subscribers", "_error_subscribers"):
            subs: list[Callable] = getattr(self, attr)
            if callback in subs:
                subs.remove(callback)

    # -- State machine helpers --------------------------------------------

    @property
    def state(self) -> ConnectionState:
        with self._lock:
            return self._state

    @property
    def is_connected(self) -> bool:
        """Whether a connection is currently live (strictly CONNECTED)."""
        with self._lock:
            return self._state is ConnectionState.CONNECTED

    @property
    def status(self) -> ConnectionStatus:
        """A snapshot of the current connection state."""
        with self._lock:
            return ConnectionStatus(self._state, self._status_message)

    def _set_state(self, new_state: ConnectionState, message: str) -> None:
        """Validate and apply a state transition, notifying subscribers."""
        subs: list[StatusCallback]
        msg: str
        state: ConnectionState
        with self._lock:
            cur = self._state
            if new_state is cur:
                self._status_message = message
                subs = list(self._status_subscribers)
                msg = message
                state = new_state
            else:
                allowed = _ALLOWED_TRANSITIONS.get(cur, set())
                if new_state not in allowed:
                    raise SerialMonitorError(
                        f"Invalid state transition {cur.value} -> {new_state.value}"
                    )
                self._state = new_state
                self._status_message = message
                subs = list(self._status_subscribers)
                msg = message
                state = new_state
        for cb in subs:
            try:
                cb(state, msg)
            except Exception:  # noqa: BLE001
                logger.exception("Status subscriber raised")

    def _notify_status(self, state: ConnectionState, message: str) -> None:
        for callback in list(self._status_subscribers):
            try:
                callback(state, message)
            except Exception:  # noqa: BLE001
                logger.exception("Status subscriber raised")

    # -- Connection lifecycle ---------------------------------------------

    def open_connection(self, port: str, baudrate: int = 9600, **kwargs: object) -> None:
        """Open the given port, start the reader thread and notify subscribers.

        Any in-flight reconnect attempt is cancelled first, so an explicit user
        action always wins.  Raises on failure; the caller is expected to
        translate the exception into a user-facing message.
        """
        with self._lock:
            self._cancel_reconnect_locked()
            if self._state not in (
                ConnectionState.DISCONNECTED,
                ConnectionState.ERROR,
            ):
                raise SerialMonitorError(f"Cannot open: current state is {self._state.value}")

        self._set_state(ConnectionState.CONNECTING, f"Connecting to {port}...")
        try:
            with self._lock:
                self._open_locked(port, baudrate, dict(kwargs))
        except Exception as exc:  # noqa: BLE001
            try:
                self._set_state(ConnectionState.ERROR, f"Connection failed: {exc}")
            except SerialMonitorError:
                with self._lock:
                    self._state = ConnectionState.ERROR
                    self._status_message = f"Connection failed: {exc}"
                self._notify_status(ConnectionState.ERROR, f"Connection failed: {exc}")
            raise
        self._set_state(ConnectionState.CONNECTED, f"Connected to {port} @ {baudrate} baud")

    def _open_locked(self, port: str, baudrate: int, kwargs: dict[str, object]) -> None:
        """Open a session and start the reader thread (caller holds the lock).

        DTR/RTS are captured as the manager's *desired* line state.  Once a
        desired level is known it wins over anything carried by ``kwargs`` or the
        source config, so a live toggle survives a manual or automatic reconnect.

        This is a pure work step: it does NOT change ConnectionState.
        """
        # Seed the desired line state from explicit kwargs only when we don't
        # already know it (a live toggle takes precedence over stale kwargs).
        if self._dtr is None:
            requested = kwargs.get("dtr", None)
            if isinstance(requested, bool):
                self._dtr = requested
        if self._rts is None:
            requested = kwargs.get("rts", None)
            if isinstance(requested, bool):
                self._rts = requested
        session = SerialSession(port, baudrate=baudrate, **kwargs)  # type: ignore[arg-type]
        # A config-driven session may resolve dtr/rts we don't know about yet.
        if self._dtr is None and session.dtr is not None:
            self._dtr = session.dtr
        if self._rts is None and session.rts is not None:
            self._rts = session.rts
        # Re-assert the desired line levels on the freshly opened session.
        if self._dtr is not None:
            session.set_dtr(self._dtr)
        if self._rts is not None:
            session.set_rts(self._rts)
        session.open()
        self._session = session
        self._status_message = f"Connected to {port} @ {baudrate} baud"
        self._last_open = (port, baudrate, dict(kwargs))
        self._start_worker()
        logger.info(self._status_message)

    def close_connection(self) -> None:
        """Stop the reader thread, close the session and notify subscribers.

        Any in-flight reconnect attempt is cancelled first.
        """
        with self._lock:
            if self._state is ConnectionState.DISCONNECTED:
                self._cancel_reconnect_locked()
                return
            if self._state is ConnectionState.DISCONNECTING:
                return
            prev_state = self._state
        try:
            self._set_state(ConnectionState.DISCONNECTING, "Disconnecting...")
        except SerialMonitorError:
            logger.warning("Forced DISCONNECTING from %s", prev_state)
            with self._lock:
                self._state = ConnectionState.DISCONNECTING
                self._status_message = "Disconnecting..."
            self._notify_status(ConnectionState.DISCONNECTING, "Disconnecting...")
        with self._lock:
            reconnect_thread = self._reconnect_thread
            self._cancel_reconnect_locked()
            if self._worker is not None:
                self._worker.stop()
                self._worker.join(timeout=2.0)
                self._worker = None
            if self._session is not None:
                try:
                    self._session.close()
                except Exception:  # noqa: BLE001
                    logger.debug("Error closing session on disconnect", exc_info=True)
                self._session = None
            self._last_open = None
            logger.info("Disconnected")
        try:
            self._set_state(ConnectionState.DISCONNECTED, "Disconnected")
        except SerialMonitorError:
            with self._lock:
                self._state = ConnectionState.DISCONNECTED
                self._status_message = "Disconnected"
            self._notify_status(ConnectionState.DISCONNECTED, "Disconnected")
        if reconnect_thread is not None and reconnect_thread is not threading.current_thread():
            reconnect_thread.join(timeout=2.0)

    def write(self, data: bytes) -> int:
        """Write *data* to the open port, returning bytes written."""
        if not data:
            return 0
        with self._lock:
            if self._state is not ConnectionState.CONNECTED or self._session is None:
                raise SerialMonitorError("Cannot write: serial port is not open")
            return self._session.write(data)

    def list_ports(self) -> list[PortInfo]:
        """Return the currently available serial ports."""
        return list_serial_ports()

    # -- Line control -------------------------------------------------------

    def set_dtr(self, enabled: bool) -> None:
        """Set the desired DTR level, applying it live while connected."""
        with self._lock:
            self._dtr = enabled
            if self._session is not None and self._state is ConnectionState.CONNECTED:
                self._session.set_dtr(enabled)

    def set_rts(self, enabled: bool) -> None:
        """Set the desired RTS level, applying it live while connected."""
        with self._lock:
            self._rts = enabled
            if self._session is not None and self._state is ConnectionState.CONNECTED:
                self._session.set_rts(enabled)

    def get_dtr(self) -> bool | None:
        """Return the desired DTR level (``None`` = driver default)."""
        return self._dtr

    def get_rts(self) -> bool | None:
        """Return the desired RTS level (``None`` = driver default)."""
        return self._rts

    def line_state(self) -> LineState:
        """Return the live DTR/RTS snapshot, falling back to the desired state."""
        with self._lock:
            if self._session is not None and self._state is ConnectionState.CONNECTED:
                return self._session.line_state()
            return LineState(self._dtr, self._rts)

    # -- Reconnection -------------------------------------------------------

    def set_reconnect_enabled(self, enabled: bool) -> None:
        """Enable/disable automatic reconnection after an unexpected disconnect."""
        self._reconnect_enabled = bool(enabled)

    @property
    def reconnect_enabled(self) -> bool:
        """Whether automatic reconnection is enabled."""
        return self._reconnect_enabled

    def set_reconnect_interval(self, interval: float) -> None:
        """Set the retry interval (seconds) used while waiting for a device."""
        self._reconnect_interval = max(0.0, float(interval))

    @property
    def reconnect_interval(self) -> float:
        """Retry interval (seconds) used while waiting for a device."""
        return self._reconnect_interval

    @staticmethod
    def _default_port_presence_check(port: str) -> bool:
        """Return whether *port* is currently visible in the OS port list."""
        return any(info.device == port for info in list_serial_ports())

    def _port_present(self, port: str) -> bool:
        """Robustly answer whether *port* is present right now."""
        try:
            return self._port_presence_check(port)
        except Exception:  # noqa: BLE001 -- a failing poll behaves as "absent"
            logger.debug("Port presence check failed for %s", port, exc_info=True)
            return False

    def _cancel_reconnect_locked(self) -> None:
        """Cancel any in-flight reconnect attempt (caller holds ``self._lock``)."""
        if self._reconnect_stop_event is not None:
            self._reconnect_stop_event.set()
        self._reconnect_thread = None

    def _start_reconnect(self) -> None:
        """Spawn a daemon thread that retries the last connection with backoff."""
        with self._lock:
            if not self._reconnect_enabled or self._last_open is None:
                return
            if self._reconnect_thread is not None and self._reconnect_thread.is_alive():
                return
            port, baudrate, kwargs = self._last_open
            stop_event = threading.Event()
            self._reconnect_stop_event = stop_event
            thread = threading.Thread(
                target=self._reconnect_loop,
                args=(port, baudrate, kwargs, stop_event),
                name="serial-reconnect",
                daemon=True,
            )
            self._reconnect_thread = thread
        try:
            self._set_state(ConnectionState.RECONNECTING, f"Reconnecting to {port}...")
        except SerialMonitorError:
            logger.warning("Invalid RECONNECTING transition from %s", self.state)
            with self._lock:
                self._state = ConnectionState.RECONNECTING
                self._status_message = f"Reconnecting to {port}..."
            self._notify_status(ConnectionState.RECONNECTING, f"Reconnecting to {port}...")
        thread.start()

    def _reconnect_loop(
        self,
        port: str,
        baudrate: int,
        kwargs: dict[str, object],
        stop_event: threading.Event,
    ) -> None:
        """Reconnect to *port* once it reappears, using exponential backoff.

        While the device is absent the loop waits, polling every
        ``reconnect_interval`` seconds; once the device is present it attempts to
        reopen under the policy's backoff.  Status changes are emitted only when
        the phase (waiting -> connecting) or the final result changes, so a
        missing device produces no log/UI spam.
        """
        self._reconnect_policy.reset()
        phase: str | None = None
        try:
            while not stop_event.is_set():
                if not self._port_present(port):
                    if phase != "waiting":
                        phase = "waiting"
                        msg = f"Reconnecting to {port}… waiting for device"
                        with self._lock:
                            self._status_message = msg
                        if self._state is not ConnectionState.RECONNECTING:
                            try:
                                self._set_state(ConnectionState.RECONNECTING, msg)
                            except SerialMonitorError:
                                with self._lock:
                                    self._state = ConnectionState.RECONNECTING
                                    self._status_message = msg
                                self._notify_status(ConnectionState.RECONNECTING, msg)
                        else:
                            self._notify_status(ConnectionState.RECONNECTING, msg)
                        logger.info(msg)
                    if stop_event.wait(self._reconnect_interval):
                        return
                    continue

                delay = self._reconnect_policy.next_delay()
                if delay < 0:
                    break
                if phase != "connecting":
                    phase = "connecting"
                    msg = f"Reconnecting to {port}..."
                    with self._lock:
                        self._status_message = msg
                    if self._state is not ConnectionState.RECONNECTING:
                        try:
                            self._set_state(ConnectionState.RECONNECTING, msg)
                        except SerialMonitorError:
                            with self._lock:
                                self._state = ConnectionState.RECONNECTING
                                self._status_message = msg
                            self._notify_status(ConnectionState.RECONNECTING, msg)
                    else:
                        self._notify_status(ConnectionState.RECONNECTING, msg)
                    logger.info(msg)
                if stop_event.wait(delay):
                    return
                if self._try_reopen(port, baudrate, kwargs):
                    return

            attempts = self._reconnect_policy.attempt
            msg2 = f"Disconnected: reconnect to {port} failed after {attempts} attempt(s)"
            try:
                self._set_state(ConnectionState.ERROR, msg2)
            except SerialMonitorError:
                with self._lock:
                    self._state = ConnectionState.ERROR
                    self._status_message = msg2
                self._notify_status(ConnectionState.ERROR, msg2)
            logger.warning(msg2)
        finally:
            if self._reconnect_thread is threading.current_thread():
                self._reconnect_thread = None

    def _try_reopen(self, port: str, baudrate: int, kwargs: dict[str, object]) -> bool:
        """Attempt to reopen *port*; returns ``True`` when handled (success/cancelled)."""
        with self._lock:
            if self._reconnect_stop_event is None or self._reconnect_stop_event.is_set():
                return True
            if self._state is ConnectionState.CONNECTED:
                return True
            if self._state not in (ConnectionState.RECONNECTING, ConnectionState.ERROR):
                return True
            try:
                self._open_locked(port, baudrate, kwargs)
            except Exception as exc:  # noqa: BLE001 -- any failure is a retryable attempt
                logger.warning("Reconnect attempt %d failed: %s", self._reconnect_policy.attempt, exc)
                self._reconnect_policy.increment()
                return False
        try:
            self._set_state(ConnectionState.CONNECTED, f"Connected to {port} @ {baudrate} baud")
        except SerialMonitorError:
            with self._lock:
                self._state = ConnectionState.CONNECTED
                self._status_message = f"Connected to {port} @ {baudrate} baud"
            self._notify_status(ConnectionState.CONNECTED, f"Connected to {port} @ {baudrate} baud")
        return True

    # -- Reader thread -----------------------------------------------------

    def _start_worker(self) -> None:
        assert self._session is not None
        port = getattr(self._session, "port", None)
        if port is None and self._last_open is not None:
            port = self._last_open[0]
        worker = SerialReaderWorker(
            self._session,
            read_callback=self._handle_data,
            error_callback=self._handle_error,
            buffer_size=self._buffer_size,
            poll_interval=self._poll_interval,
            port=port,
            port_check=(lambda: self._port_present(port)) if port else None,
            port_check_interval=1.0,
        )
        self._worker = worker
        worker.start()

    def _handle_data(self, data: bytes) -> None:
        for callback in list(self._data_subscribers):
            try:
                callback(data)
            except Exception:
                logger.exception("Data subscriber raised")

    def _handle_error(self, exc: Exception) -> None:
        """Handle an async read failure (invoked from the reader thread).

        State transitions (``_state``, ``_session``, ``_worker``) are guarded
        by ``self._lock`` so they never race with a user-initiated connect or
        disconnect on the main thread.  The session is closed *outside* the lock:
        a driver close can block, and the reader thread is already exiting, so no
        further reads will occur.

        When auto-reconnect is enabled and the device simply vanished
        (``SerialPortNotFoundError``), the reconnect loop is the intended response
        and the error is *not* forwarded to ``_error_subscribers`` -- otherwise a
        routine unplug would pop a modal dialog from the UI on every disconnect.
        """
        with self._lock:
            was_connected = self._state is ConnectionState.CONNECTED
            session = self._session
            self._session = None
            self._worker = None
            suppressed = (
                self._reconnect_enabled
                and was_connected
                and self._last_open is not None
                and isinstance(exc, SerialPortNotFoundError)
            )

        if session is not None:
            try:
                session.close()
            except Exception as close_exc:  # noqa: BLE001 -- never mask the original error
                logger.debug("Error closing session after read failure: %s", close_exc)

        try:
            self._set_state(ConnectionState.ERROR, f"Disconnected: {exc}")
        except SerialMonitorError:
            with self._lock:
                self._state = ConnectionState.ERROR
                self._status_message = f"Disconnected: {exc}"
            self._notify_status(ConnectionState.ERROR, f"Disconnected: {exc}")
        if suppressed:
            logger.info("Disconnected: %s", exc)
        else:
            for callback in list(self._error_subscribers):
                try:
                    callback(exc)
                except Exception:  # noqa: BLE001
                    logger.exception("Error subscriber raised")
        if self._reconnect_enabled and was_connected and self._last_open is not None:
            self._start_reconnect()


