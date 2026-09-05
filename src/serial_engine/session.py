"""Low level serial connection session.

Wraps a single ``serial.Serial`` instance behind a small, stable interface and
translates pyserial exceptions into the application's exception hierarchy.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

import serial

from .config import SerialSessionConfig
from .exceptions import (
    SerialConfigError,
    SerialConnectionError,
    SerialReadError,
    SerialWriteError,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LineState:
    """A snapshot of the generic RS-232 line-control levels.

    ``None`` means "no explicit level was requested", so the driver keeps its
    platform default rather than asserting/deasserting a line.
    """

    dtr: bool | None
    rts: bool | None


class SessionProtocol(Protocol):
    """Structural interface for a serial session (duck-typed).

    ``SerialSession`` satisfies this protocol, and so can lightweight test fakes.
    Kept free of Qt and of any pyserial types so the engine stays hardware-agnostic.
    """

    #: Whether the underlying port is open.
    @property
    def is_open(self) -> bool: ...

    def open(self) -> None: ...
    def close(self) -> None: ...
    def write(self, data: bytes) -> int: ...
    def in_waiting(self) -> int: ...
    def read(self, size: int = 1) -> bytes: ...
    def set_dtr(self, enabled: bool) -> None: ...
    def set_rts(self, enabled: bool) -> None: ...
    def get_dtr(self) -> bool | None: ...
    def get_rts(self) -> bool | None: ...
    def line_state(self) -> LineState: ...


class SerialSession:
    """Own a single open serial port connection."""

    def __init__(
        self,
        port: str = "",
        baudrate: int = 9600,
        *,
        config: SerialSessionConfig | None = None,
        bytesize: int = serial.EIGHTBITS,
        parity: str = serial.PARITY_NONE,
        stopbits: float = serial.STOPBITS_ONE,
        timeout: float | None = 0.1,
        write_timeout: float | None = 2.0,
        dtr: bool | None = None,
        rts: bool | None = None,
    ) -> None:
        if config is not None:
            # A config drives every serial parameter.  The explicit ``port`` wins
            # when provided, otherwise the config's port is used.
            ser = config.to_pyserial_kwargs()  # validates; raises SerialConfigError
            self._config = config
            self.port = port or config.port
            self.baudrate = config.baudrate
            self.bytesize = ser["bytesize"]
            self.parity = ser["parity"]
            self.stopbits = ser["stopbits"]
            self._xonxoff = ser["xonxoff"]
            self._rtscts = ser["rtscts"]
            self._dsrdtr = ser["dsrdtr"]
            self.dtr = config.dtr if dtr is None else dtr
            self.rts = config.rts if rts is None else rts
        else:
            self._config = None
            self.port = port
            self.baudrate = baudrate
            self.bytesize = bytesize
            self.parity = parity
            self.stopbits = stopbits
            self._xonxoff = False
            self._rtscts = False
            self._dsrdtr = False
            self.dtr = dtr
            self.rts = rts
        self.timeout = timeout
        self.write_timeout = write_timeout
        self._serial: serial.Serial | None = None

    @property
    def is_open(self) -> bool:
        """Whether the underlying port is currently open."""
        return self._serial is not None and self._serial.is_open

    def open(self) -> None:
        """Open the serial port.

        :raises SerialConfigError: if no ``port`` was configured.
        :raises SerialConnectionError: if the OS cannot open the port.
        """
        if self.is_open:
            logger.debug("Serial port %s is already open", self.port)
            return
        if not self.port:
            raise SerialConfigError("No serial port configured")
        try:
            self._serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=self.bytesize,
                parity=self.parity,
                stopbits=self.stopbits,
                timeout=self.timeout,
                write_timeout=self.write_timeout,
                xonxoff=self._xonxoff,
                rtscts=self._rtscts,
                dsrdtr=self._dsrdtr,
            )
        except (ValueError, serial.SerialException) as exc:
            if isinstance(exc, ValueError):
                # Invalid parameter/combination rejected by pyserial.
                logger.error("Invalid config for %s: %s", self.port, exc)
                raise SerialConfigError(f"Invalid serial configuration: {exc}") from exc
            logger.error("Failed to open %s: %s", self.port, exc)
            raise SerialConnectionError(f"Could not open {self.port}: {exc}") from exc
        self._apply_line_settings()
        self._flush_input()
        logger.info("Opened serial port %s @ %d baud", self.port, self.baudrate)

    def _apply_line_settings(self) -> None:
        """Apply the optional DTR/RTS line states, tolerating driver quirks."""
        if self._serial is None:
            return
        if self.dtr is not None:
            try:
                self._serial.dtr = self.dtr
            except serial.SerialException as exc:  # pragma: no cover - driver dependent
                logger.warning("Could not set DTR=%s on %s: %s", self.dtr, self.port, exc)
        if self.rts is not None:
            try:
                self._serial.rts = self.rts
            except serial.SerialException as exc:  # pragma: no cover - driver dependent
                logger.warning("Could not set RTS=%s on %s: %s", self.rts, self.port, exc)

    def _flush_input(self) -> None:
        """Discard any stale input bytes that accumulated before this session opened.

        This is best-effort: some USB-to-UART bridges/drivers don't expose or
        fully honour ``serial.Serial.reset_input_buffer()``, so any rejection is
        logged and ignored rather than failing the open.
        """
        serial_obj = self._serial
        if serial_obj is None:
            return
        reset = getattr(serial_obj, "reset_input_buffer", None)
        if not callable(reset):
            return
        try:
            reset()
        except serial.SerialException as exc:  # pragma: no cover - driver dependent
            logger.warning("Could not flush input buffer on %s: %s", self.port, exc)

    @classmethod
    def from_config(
        cls,
        config: SerialSessionConfig,
        *,
        timeout: float | None = 0.1,
        write_timeout: float | None = 2.0,
    ) -> SerialSession:
        """Create a session configured from *config*."""
        return cls(config=config, timeout=timeout, write_timeout=write_timeout)

    def apply_config(self, config: SerialSessionConfig) -> None:
        """Validate and apply *config* to this session.

        The config is validated (raising :class:`SerialConfigError` on unsupported
        values or combinations) and its values are stored on the session.  If the
        port is currently open, an attempt is made to reconfigure it live; any
        driver-level rejection is translated into :class:`SerialConfigError`.
        """
        ser = config.to_pyserial_kwargs()  # validates; raises SerialConfigError
        self._config = config
        self.port = config.port or self.port
        self.baudrate = config.baudrate
        self.bytesize = ser["bytesize"]
        self.parity = ser["parity"]
        self.stopbits = ser["stopbits"]
        self._xonxoff = ser["xonxoff"]
        self._rtscts = ser["rtscts"]
        self._dsrdtr = ser["dsrdtr"]
        self.dtr = config.dtr
        self.rts = config.rts
        if self._serial is not None and self._serial.is_open:
            try:
                self._serial.baudrate = config.baudrate
                self._serial.bytesize = ser["bytesize"]
                self._serial.parity = ser["parity"]
                self._serial.stopbits = ser["stopbits"]
                self._serial.xonxoff = ser["xonxoff"]
                self._serial.rtscts = ser["rtscts"]
                self._serial.dsrdtr = ser["dsrdtr"]
                # pyserial may require an explicit apply() on some platforms once
                # attributes are changed on an open port.
                apply = getattr(self._serial, "apply", None)
                if callable(apply):
                    apply()
                self._apply_line_settings()
            except (ValueError, serial.SerialException) as exc:
                logger.warning("Could not apply config to %s: %s", self.port, exc)
                raise SerialConfigError(f"Could not apply configuration: {exc}") from exc
        logger.debug(
            "Applied serial config (port=%s @ %d baud)", self.port, self.baudrate
        )

    def close(self) -> None:
        """Close the serial port (idempotent).

        :raises SerialConnectionError: if the OS reports an error on close.
        """
        if self._serial is None:
            return
        try:
            self._serial.close()
        except serial.SerialException as exc:
            logger.warning("Error closing %s: %s", self.port, exc)
            raise SerialConnectionError(f"Could not close {self.port}: {exc}") from exc
        finally:
            self._serial = None
            logger.info("Closed serial port %s", self.port)

    def read(self, size: int = 1) -> bytes:
        """Read up to *size* bytes from the port."""
        if self._serial is None:
            raise SerialConnectionError("Serial port is not open")
        try:
            return self._serial.read(size)
        except serial.SerialException as exc:
            raise SerialReadError(f"Read failed: {exc}") from exc

    def write(self, data: bytes) -> int:
        """Write *data* and flush; returns the number of bytes written."""
        if self._serial is None:
            raise SerialConnectionError("Serial port is not open")
        if not data:
            return 0
        try:
            written = self._serial.write(data)
            self._serial.flush()
            return written or 0
        except serial.SerialException as exc:
            raise SerialWriteError(f"Write failed: {exc}") from exc

    def in_waiting(self) -> int:
        """Return the number of bytes currently buffered for reading."""
        if self._serial is None:
            return 0
        try:
            return self._serial.in_waiting
        except serial.SerialException as exc:
            raise SerialReadError(f"in_waiting failed: {exc}") from exc

    def set_dtr(self, enabled: bool) -> None:
        """Set the DTR line level, applying it live while the port is open.

        ``enabled`` is remembered on the session so it is re-asserted on any
        subsequent (re)open.
        """
        self.dtr = enabled
        self._apply_line("dtr", enabled)

    def set_rts(self, enabled: bool) -> None:
        """Set the RTS line level, applying it live while the port is open."""
        self.rts = enabled
        self._apply_line("rts", enabled)

    def get_dtr(self) -> bool | None:
        """Return the current desired DTR level (``None`` = driver default)."""
        return self.dtr

    def get_rts(self) -> bool | None:
        """Return the current desired RTS level (``None`` = driver default)."""
        return self.rts

    def line_state(self) -> LineState:
        """Return a snapshot of the DTR/RTS line levels."""
        return LineState(dtr=self.dtr, rts=self.rts)

    def _apply_line(self, name: str, enabled: bool) -> None:
        """Push a single line level to the live port, tolerating driver quirks."""
        if self._serial is None or not self._serial.is_open:
            return
        try:
            setattr(self._serial, name, enabled)
        except serial.SerialException as exc:  # pragma: no cover - driver dependent
            logger.warning("Could not set %s=%s on %s: %s", name, enabled, self.port, exc)

    def __enter__(self) -> SerialSession:  # noqa: PYI034 -- typing.Self needs 3.11; keep 3.10
        """Context-manager support."""
        self.open()
        return self

    def __exit__(self, *exc: object) -> None:
        """Context-manager support."""
        self.close()
