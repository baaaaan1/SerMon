"""Shared UI state container."""

from __future__ import annotations

from dataclasses import dataclass, field

from serial_engine.manager import ConnectionState
from serial_engine.port_scanner import PortInfo


@dataclass
class AppState:
    """State shared across widgets.

    This holds UI-relevant values only; it deliberately has no Qt or serial
    dependencies, which keeps it easy to test.
    """

    port: str = ""
    baudrate: int = 9600
    parser: str = "line"
    connection_state: ConnectionState = ConnectionState.DISCONNECTED
    last_error: str = ""
    available_ports: list[PortInfo] = field(default_factory=list)
    received_bytes: int = 0
    sent_bytes: int = 0

    @property
    def connected(self) -> bool:
        return self.connection_state is ConnectionState.CONNECTED

    @connected.setter
    def connected(self, value: bool) -> None:
        self.connection_state = ConnectionState.CONNECTED if value else ConnectionState.DISCONNECTED
