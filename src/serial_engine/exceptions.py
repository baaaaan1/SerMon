"""Exception hierarchy for the serial engine.

All serial-related errors derive from :class:`SerialMonitorError`, so callers
can catch a single base class and still branch on the specific failure mode.
"""

from __future__ import annotations


class SerialMonitorError(Exception):
    """Base class for every error raised by the serial engine."""


class SerialConnectionError(SerialMonitorError):
    """A serial connection could not be opened or closed cleanly."""


class SerialConfigError(SerialMonitorError):
    """The serial configuration is invalid or incomplete."""


class SerialReadError(SerialMonitorError):
    """Reading from the serial port failed."""


class SerialWriteError(SerialMonitorError):
    """Writing to the serial port failed."""


class SerialPortNotFoundError(SerialConnectionError):
    """The requested serial port no longer exists."""
