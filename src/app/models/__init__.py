"""UI sub-package: view models used by widgets.

These classes contain the application's display/behaviour logic but no Qt
components, so they can be tested in isolation.
"""

from __future__ import annotations

from .quick_commands import QuickCommandsModel
from .terminal import (
    DEFAULT_MAX_LINES,
    LINE_ENDINGS,
    SCROLLBACK_LIMITS,
    TerminalOptions,
    TerminalViewModel,
)
from .tx_input import DEFAULT_HISTORY_SIZE, TxHistory

__all__ = [
    "DEFAULT_HISTORY_SIZE",
    "DEFAULT_MAX_LINES",
    "LINE_ENDINGS",
    "SCROLLBACK_LIMITS",
    "QuickCommandsModel",
    "TerminalOptions",
    "TerminalViewModel",
    "TxHistory",
]


