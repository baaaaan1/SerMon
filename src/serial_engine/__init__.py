"""Serial engine (Qt-free).

This package intentionally has **no PySide6 dependency**.  It depends only on
``pyserial`` and the Python standard library, so the communication layer can be
unit-tested and reused independently of any GUI toolkit.
"""

from .config import (
    SUPPORTED_BAUDRATES,
    SUPPORTED_DATA_BITS,
    SUPPORTED_DISPLAY_MODES,
    SUPPORTED_FLOW_CONTROL,
    SUPPORTED_PARITIES,
    SUPPORTED_STOP_BITS,
    SerialSessionConfig,
)
from .exceptions import (
    SerialConfigError,
    SerialConnectionError,
    SerialMonitorError,
    SerialPortNotFoundError,
    SerialReadError,
    SerialWriteError,
)
from .manager import ConnectionState, SerialManager
from .port_scanner import PortInfo, list_serial_ports
from .session import SessionProtocol

__all__ = [
    "SUPPORTED_BAUDRATES",
    "SUPPORTED_DATA_BITS",
    "SUPPORTED_DISPLAY_MODES",
    "SUPPORTED_FLOW_CONTROL",
    "SUPPORTED_PARITIES",
    "SUPPORTED_STOP_BITS",
    "ConnectionState",
    "PortInfo",
    "SerialConfigError",
    "SerialConnectionError",
    "SerialManager",
    "SerialMonitorError",
    "SerialPortNotFoundError",
    "SerialReadError",
    "SerialSessionConfig",
    "SerialWriteError",
    "SessionProtocol",
    "list_serial_ports",
]
