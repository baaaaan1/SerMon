"""Discover available serial ports.

This module wraps ``serial.tools.list_ports`` and returns portable
:class:`PortInfo` dataclasses, so the rest of the application never has to deal
with pyserial's internal representation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from serial.tools import list_ports
from serial.tools.list_ports_common import ListPortInfo

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PortInfo:
    """Normalised description of an available serial port."""

    device: str
    description: str = ""
    hwid: str = ""
    vid: int | None = None
    pid: int | None = None
    manufacturer: str | None = None
    product: str | None = None
    interface: str | None = None

    @property
    def label(self) -> str:
        """A human friendly label suitable for a drop-down."""
        if self.description:
            return f"{self.device} — {self.description}"
        return self.device

    @classmethod
    def from_list_port(cls, port: ListPortInfo) -> PortInfo:
        """Build a :class:`PortInfo` from a pyserial list-port entry."""
        return cls(
            device=port.device,
            description=port.description or "",
            hwid=port.hwid or "",
            vid=port.vid,
            pid=port.pid,
            manufacturer=port.manufacturer,
            product=port.product,
            interface=port.interface,
        )


def list_serial_ports() -> list[PortInfo]:
    """Return a sorted list of currently available serial ports.

    Every enumerated port is included regardless of the underlying USB-to-UART
    bridge, FPGA, MCU or vendor — no chipset/MCU filtering is applied.  On
    platforms where enumeration raises (e.g. a blocked driver), the function logs
    the problem and returns an empty list instead of propagating.
    """
    try:
        ports = sorted(
            (PortInfo.from_list_port(p) for p in list_ports.comports()),
            key=lambda p: p.device,
        )
    except Exception:  # pragma: no cover - defensive on unusual platforms
        logger.exception("Failed to enumerate serial ports")
        return []
    logger.debug("Discovered %d serial port(s)", len(ports))
    return ports
