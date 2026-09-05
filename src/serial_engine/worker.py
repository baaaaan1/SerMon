"""Background reader thread.

A single daemon thread that continuously pulls available bytes from a
:class:`SerialSession` and hands them to a plain-Python callback.  The worker is
completely agnostic of Qt: it only talks to a session and callables.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

from .exceptions import SerialMonitorError, SerialPortNotFoundError
from .session import SessionProtocol

logger = logging.getLogger(__name__)

#: Receives a chunk of raw bytes read from the port.
ReadCallback = Callable[[bytes], None]
#: Receives an exception raised while reading.
ErrorCallback = Callable[[Exception], None]


class SerialReaderWorker(threading.Thread):
    """Daemon thread that reads from a session until it is asked to stop."""

    def __init__(
        self,
        session: SessionProtocol,
        *,
        read_callback: ReadCallback,
        error_callback: ErrorCallback | None = None,
        buffer_size: int = 4096,
        poll_interval: float = 0.01,
        port: str | None = None,
        port_check: Callable[[], bool] | None = None,
        port_check_interval: float | None = None,
    ) -> None:
        super().__init__(name="serial-reader", daemon=True)
        self._session = session
        self._read_callback = read_callback
        self._error_callback = error_callback
        self._buffer_size = buffer_size
        self._poll_interval = poll_interval
        self._stop_event = threading.Event()
        self._port = port
        self._port_check = port_check
        self._port_check_interval = port_check_interval if port_check_interval is not None else 0.0
        #: Number of poll ticks between port-presence checks (0 = disabled).
        self._port_check_ticks = (
            max(1, int(round(self._port_check_interval / self._poll_interval)))
            if (port_check is not None and self._port_check_interval > 0.0)
            else 0
        )

    def stop(self) -> None:
        """Request the worker to halt at the next opportunity."""
        self._stop_event.set()

    def run(self) -> None:  # pragma: no cover - exercised via tests of manager
        logger.debug("Serial reader thread started")
        tick = 0
        try:
            while not self._stop_event.is_set():
                # Watch for the device being unplugged *before* touching the
                # session, so a removed port is detected even if the driver has
                # already marked the session closed.
                if self._port_check is not None and self._port_check_ticks:
                    tick += 1
                    if tick >= self._port_check_ticks:
                        tick = 0
                        if not self._port_check():
                            self._forward_error(
                                SerialPortNotFoundError(
                                    f"Serial port {self._port} was removed"
                                )
                            )
                            break
                if not self._session.is_open:
                    self._wait_or_stop()
                    continue
                try:
                    in_wait = self._session.in_waiting()
                except SerialMonitorError as exc:
                    self._forward_error(exc)
                    break

                if in_wait:
                    data = self._session.read(min(self._buffer_size, in_wait))
                    if data:
                        self._read_callback(data)
                else:
                    self._wait_or_stop()
        except SerialMonitorError as exc:
            self._forward_error(exc)
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Unexpected error in serial reader")
            self._forward_error(exc)
        finally:
            logger.debug("Serial reader thread stopped")

    def _wait_or_stop(self) -> None:
        """Sleep until a stop is requested or the poll interval elapses."""
        self._stop_event.wait(self._poll_interval)

    def _forward_error(self, exc: Exception) -> None:
        logger.error("Serial reader error: %s", exc)
        if self._error_callback is not None:
            self._error_callback(exc)
