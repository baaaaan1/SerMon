"""Generic, MCU-agnostic serial session configuration model.

This module defines the *configuration* for a serial session as a first-class,
validated object.  It deliberately contains **no MCU-specific assumptions**: the
supported values are the standard, cross-platform set that any UART (AVR, STM32,
ESP32, CH340, FTDI, ...) can address, and the model never hard-codes a particular
chip's quirks.  The module is also Qt-free, so it can be reused by any front-end.

Readable values are mapped onto pyserial's constants only at the moment the
session is opened (see :meth:`SerialSessionConfig.to_pyserial_kwargs`).
Unsupported values or combinations raise :class:`SerialConfigError` instead of
being silently accepted or blowing up later inside pyserial.
"""

from __future__ import annotations

import codecs
from dataclasses import dataclass
from typing import TypedDict

import serial

from .exceptions import SerialConfigError

#: Standard, MCU-agnostic baud rates offered to the user.
SUPPORTED_BAUDRATES: tuple[int, ...] = (
    1200,
    2400,
    4800,
    9600,
    19200,
    38400,
    57600,
    115200,
    230400,
    460800,
    921600,
)

#: Data bits supported by the generic model (pyserial also allows 5/6).
SUPPORTED_DATA_BITS: tuple[int, ...] = (7, 8)

#: Parity settings, using human-readable (not pyserial single-char) values.
SUPPORTED_PARITIES: tuple[str, ...] = ("None", "Even", "Odd", "Mark", "Space")

#: Stop bit values. ``1.5`` is allowed as a *parameter* but is rejected as a
#: combination with the supported data bits (see :meth:`validate`).
SUPPORTED_STOP_BITS: tuple[float, ...] = (1.0, 1.5, 2.0)

#: Flow-control modes, mapped onto pyserial's ``xonxoff``/``rtscts``/``dsrdtr``.
SUPPORTED_FLOW_CONTROL: tuple[str, ...] = ("None", "RTS/CTS", "XON/XOFF", "DTR/DSR")

#: How received bytes are presented (consumed by the display layer).
SUPPORTED_DISPLAY_MODES: tuple[str, ...] = ("Text", "Hex")

#: Preferred defaults, used when a config is created without arguments.
DEFAULT_BAUDRATE: int = 9600
DEFAULT_DATA_BITS: int = 8
DEFAULT_PARITY: str = "None"
DEFAULT_STOP_BITS: float = 1.0
DEFAULT_FLOW_CONTROL: str = "None"
DEFAULT_ENCODING: str = "utf-8"
DEFAULT_DISPLAY_MODE: str = "Text"

#: Canonical value -> pyserial ``parity`` constant.
_PARITY_TO_SERIAL: dict[str, str] = {
    "None": serial.PARITY_NONE,
    "Even": serial.PARITY_EVEN,
    "Odd": serial.PARITY_ODD,
    "Mark": serial.PARITY_MARK,
    "Space": serial.PARITY_SPACE,
}

#: Data bits -> pyserial ``bytesize`` constant.
_DATA_BITS_TO_SERIAL: dict[int, int] = {
    7: serial.SEVENBITS,
    8: serial.EIGHTBITS,
}

#: Stop bits -> pyserial ``stopbits`` constant.
_STOP_BITS_TO_SERIAL: dict[float, float] = {
    1.0: serial.STOPBITS_ONE,
    1.5: serial.STOPBITS_ONE_POINT_FIVE,
    2.0: serial.STOPBITS_TWO,
}

#: Flow-control mode -> pyserial keyword flags.
_FLOW_TO_PYSERIAL: dict[str, dict[str, bool]] = {
    "None": {"xonxoff": False, "rtscts": False, "dsrdtr": False},
    "RTS/CTS": {"xonxoff": False, "rtscts": True, "dsrdtr": False},
    "XON/XOFF": {"xonxoff": True, "rtscts": False, "dsrdtr": False},
    "DTR/DSR": {"xonxoff": False, "rtscts": False, "dsrdtr": True},
}


class _SerialKwargs(TypedDict):
    """Keyword arguments for ``serial.Serial``.

    ``dtr`` and ``rts`` are intentionally absent -- they are applied *after* the
    port is opened (see ``SerialSession._apply_line_settings``), never passed to
    the constructor.  Typed so keyed access yields concrete pyserial value types.
    """

    baudrate: int
    bytesize: int
    parity: str
    stopbits: float
    xonxoff: bool
    rtscts: bool
    dsrdtr: bool


@dataclass
class SerialSessionConfig:
    """Generic, validated configuration for a serial session.

    A config is MCU-agnostic: it only describes the line parameters in terms of
    standard values, never in terms of a particular microcontroller.  It can be
    created, mutated, validated and applied to a :class:`~serial_engine.session.
    SerialSession`.

    Use :meth:`validate` (called automatically from :meth:`__post_init__` and
    again from :meth:`to_pyserial_kwargs`) to guard against unsupported values or
    combinations; it raises :class:`SerialConfigError`.
    """

    port: str = ""
    baudrate: int = DEFAULT_BAUDRATE
    data_bits: int = DEFAULT_DATA_BITS
    parity: str = DEFAULT_PARITY
    stop_bits: float = DEFAULT_STOP_BITS
    flow_control: str = DEFAULT_FLOW_CONTROL
    dtr: bool | None = None
    rts: bool | None = None
    encoding: str = DEFAULT_ENCODING
    display_mode: str = DEFAULT_DISPLAY_MODE

    def __post_init__(self) -> None:
        """Validate the config as soon as it is created."""
        self.validate()

    def validate(self) -> None:
        """Check every field against the supported values and combinations.

        :raises SerialConfigError: if any value is unsupported or an invalid
            combination (e.g. ``stop_bits`` of ``1.5`` with ``data_bits`` of
            ``7``/``8``) was requested.
        """
        if self.baudrate not in SUPPORTED_BAUDRATES:
            raise SerialConfigError(
                f"Unsupported baudrate {self.baudrate!r}; "
                f"supported: {SUPPORTED_BAUDRATES}"
            )
        if self.data_bits not in SUPPORTED_DATA_BITS:
            raise SerialConfigError(
                f"Unsupported data bits {self.data_bits!r}; "
                f"supported: {SUPPORTED_DATA_BITS}"
            )
        if self.parity not in SUPPORTED_PARITIES:
            raise SerialConfigError(
                f"Unsupported parity {self.parity!r}; "
                f"supported: {SUPPORTED_PARITIES}"
            )
        if self.stop_bits not in SUPPORTED_STOP_BITS:
            raise SerialConfigError(
                f"Unsupported stop bits {self.stop_bits!r}; "
                f"supported: {SUPPORTED_STOP_BITS}"
            )
        if self.flow_control not in SUPPORTED_FLOW_CONTROL:
            raise SerialConfigError(
                f"Unsupported flow control {self.flow_control!r}; "
                f"supported: {SUPPORTED_FLOW_CONTROL}"
            )
        if self.display_mode not in SUPPORTED_DISPLAY_MODES:
            raise SerialConfigError(
                f"Unsupported display mode {self.display_mode!r}; "
                f"supported: {SUPPORTED_DISPLAY_MODES}"
            )
        if self.dtr is not None and not isinstance(self.dtr, bool):
            raise SerialConfigError("dtr must be a bool or None")
        if self.rts is not None and not isinstance(self.rts, bool):
            raise SerialConfigError("rts must be a bool or None")

        try:
            codecs.lookup(self.encoding)
        except LookupError as exc:
            raise SerialConfigError(
                f"Unknown encoding {self.encoding!r}; use a valid Python codec"
            ) from exc

        # Cross-field constraints.  pyserial only supports ``STOPBITS_ONE_POINT_FIVE``
        # for 5-bit words, so it is incompatible with the supported 7/8 data bits.
        if self.stop_bits == 1.5 and self.data_bits in (7, 8):
            raise SerialConfigError(
                "1.5 stop bits are only supported with 5 data bits; "
                f"data_bits={self.data_bits} is unsupported for this combination"
            )

    def to_pyserial_kwargs(self) -> _SerialKwargs:
        """Return the keyword arguments for ``serial.Serial``.

        ``dtr`` and ``rts`` are intentionally excluded -- they are applied *after*
        the port is opened (see ``SerialSession._apply_line_settings``), not passed
        to the constructor.
        """
        self.validate()
        flow = _FLOW_TO_PYSERIAL[self.flow_control]
        kwargs: _SerialKwargs = {
            "baudrate": self.baudrate,
            "bytesize": _DATA_BITS_TO_SERIAL[self.data_bits],
            "parity": _PARITY_TO_SERIAL[self.parity],
            "stopbits": _STOP_BITS_TO_SERIAL[self.stop_bits],
            "xonxoff": flow["xonxoff"],
            "rtscts": flow["rtscts"],
            "dsrdtr": flow["dsrdtr"],
        }
        return kwargs

