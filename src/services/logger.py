"""Application-wide logging configuration.

Configuration is driven by :class:`~services.config.AppConfig` and applied
close to application startup so every module can rely on a consistent formatter,
level and optional file handler.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .config import AppConfig

_LOGGER_NAME = "serial_monitor"
_FMT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"
_MAX_BYTES = 2_000_000
_BACKUP_COUNT = 3
_CONFIGURED = False


def configure_logging(config: AppConfig, *, force: bool = False) -> None:
    """Configure the ``serial_monitor`` logger from *config*.

    The function is idempotent unless ``force=True`` is passed.
    """
    global _CONFIGURED
    if _CONFIGURED and not force:
        return

    level = getattr(logging, str(config.log_level).upper(), logging.INFO)
    root = logging.getLogger()
    root.setLevel(level)

    formatter = logging.Formatter(_FMT, datefmt=_DATEFMT)

    # Console handler (always present).
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root.addHandler(console)

    # Optional rotating file handler.
    log_file: str | Path | None = config.log_file
    if log_file:
        try:
            path = Path(log_file)
            path.parent.mkdir(parents=True, exist_ok=True)
            file_handler = RotatingFileHandler(
                path, maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT, encoding="utf-8"
            )
            file_handler.setFormatter(formatter)
            root.addHandler(file_handler)
        except OSError as exc:
            logging.getLogger(__name__).error("Could not attach file handler: %s", exc)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a logger namespaced beneath the application logger root."""
    return logging.getLogger(f"{_LOGGER_NAME}.{name}")
