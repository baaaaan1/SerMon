"""UI sub-package: custom Qt widgets.

Widgets are thin Qt adapters over the Qt-free view-models in
:mod:`app.models`; they only contain view concerns and never import ``pyserial``.
"""

from __future__ import annotations

from .activity import ActivityIndicator, StatusDot
from .connection_panel import ConnectionPanel
from .counters import ByteCounter
from .quick_commands import QuickCommands
from .terminal import TerminalView
from .tx_input import TxInput

__all__ = [
    "ActivityIndicator",
    "ByteCounter",
    "ConnectionPanel",
    "QuickCommands",
    "StatusDot",
    "TerminalView",
    "TxInput",
]


