"""Centralised error-handling strategy.

The application routes exceptions through :func:`handle` so that they are always
logged consistently and, optionally, surfaced to user-facing handlers (e.g. a
Qt dialog or a status bar) before any re-raise.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from serial_engine.exceptions import SerialMonitorError

logger = logging.getLogger(__name__)

#: A user-facing error handler (typically UI-driven).
ErrorHandler = Callable[[Exception], None]

_handlers: list[ErrorHandler] = []


def register_handler(handler: ErrorHandler) -> None:
    """Register a user-facing error handler; called before any re-raise."""
    if handler not in _handlers:
        _handlers.append(handler)


def handle(
    error: Exception,
    *,
    context: str = "",
    re_raise: bool = False,
    raise_type: type[Exception] | None = None,
) -> None:
    """Process an exception according to the application error strategy.

    - Always logs the error (with *context* when provided).
    - Notifies registered user-facing handlers first.
    - Optionally re-raises, optionally wrapped in *raise_type*.

    :raises type(error): if ``re_raise`` is ``True``.
    :raises raise_type: if provided, the error is wrapped and re-raised.
    """
    prefix = f"[{context}] " if context else ""
    logger.error("%s%s: %s", prefix, type(error).__name__, error)

    for handler in _handlers:
        try:
            handler(error)
        except Exception:  # pragma: no cover - handler must not crash the app
            logger.exception("Error handler raised")

    if raise_type is not None:
        raise raise_type(f"{prefix}{error}") from error
    if re_raise:
        raise error


def handle_with_msg(error: Exception, *, context: str = "") -> str:
    """Log *error* and return a concise, user-facing message string."""
    if isinstance(error, SerialMonitorError):
        detail = str(error)
    else:
        detail = f"{type(error).__name__}: {error}"
    prefix = f"[{context}] " if context else ""
    logger.error("%s%s", prefix, detail)
    return detail
