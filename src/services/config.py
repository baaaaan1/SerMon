"""Application configuration management.

Config is stored as JSON and merged over built-in defaults, so new settings can
be added over time without breaking existing config files.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

#: Default location for the user's config file.
DEFAULT_CONFIG_PATH = Path.home() / ".serial_monitor" / "config.json"

#: Valid theme resolutions (must stay in sync with ``app.theme.manager.THEME_MODES``).
VALID_THEMES: tuple[str, ...] = ("light", "dark", "system")


@dataclass
class SerialConfig:
    """Connection parameters for a serial port."""

    port: str = ""
    baudrate: int = 9600
    bytesize: int = 8
    parity: str = "N"
    stopbits: float = 1.0
    read_timeout: float = 0.1
    write_timeout: float = 2.0
    dtr: bool | None = None
    rts: bool | None = None


@dataclass
class WindowConfig:
    """Persisted window geometry and maximized state.

    Negative coordinates are treated as "unset" so Qt can auto-place the window,
    while ``width``/``height`` fall back to the built-in default size.
    """

    x: int = -1
    y: int = -1
    width: int = 840
    height: int = 560
    maximized: bool = False


@dataclass
class AppConfig:
    """Top-level application configuration."""

    version: int = 1
    log_level: str = "INFO"
    log_file: str | None = None
    theme: str = "system"
    reconnect_enabled: bool = True
    reconnect_interval: float = 1.0
    parser: str = "line"
    serial: SerialConfig = field(default_factory=SerialConfig)
    window: WindowConfig = field(default_factory=WindowConfig)
    #: Preserve unknown keys so future fields survive a save/load cycle.
    custom: dict[str, Any] = field(default_factory=dict)


class ConfigManager:
    """Load and persist an :class:`AppConfig` as JSON."""

    def __init__(self, path: Path | str | None = None) -> None:
        self._path = Path(path) if path else DEFAULT_CONFIG_PATH
        self._config = self._load()

    @property
    def path(self) -> Path:
        """Location of the backing JSON file."""
        return self._path

    def get(self) -> AppConfig:
        """Return the live configuration object."""
        return self._config

    def set(self, config: AppConfig) -> None:
        """Replace the in-memory config and persist it to disk."""
        self._config = config
        self.save()

    def save(self) -> None:
        """Serialize the current config to disk."""
        data = asdict(self._config)
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, ensure_ascii=False)
        except OSError as exc:
            logger.error("Could not save config to %s: %s", self._path, exc)
        else:
            logger.info("Saved config to %s", self._path)

    def _load(self) -> AppConfig:
        """Load config from disk, falling back to defaults on any error."""
        defaults = AppConfig()
        if not self._path.exists():
            logger.info("No config file at %s; using defaults", self._path)
            return defaults
        try:
            raw: dict[str, Any] = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.error("Could not read config %s: %s", self._path, exc)
            return defaults
        return self._merge(defaults, raw)

    @staticmethod
    def _merge(defaults: AppConfig, raw: dict[str, Any]) -> AppConfig:
        """Overlay raw JSON values on top of the default config."""
        # Top-level known fields (excluding the nested ``serial``/``window`` dicts).
        for f in fields(AppConfig):
            if f.name in raw and f.name not in {"serial", "window"}:
                setattr(defaults, f.name, raw[f.name])

        # Keep the theme resolved to a known value (older configs may be "dark").
        if defaults.theme not in VALID_THEMES:
            defaults.theme = "system"

        # Merge the nested serial settings.
        serial_raw = raw.get("serial") or {}
        if not isinstance(serial_raw, dict):
            serial_raw = {}
        for f in fields(SerialConfig):
            if f.name in serial_raw:
                setattr(defaults.serial, f.name, serial_raw[f.name])

        # Merge the nested window geometry settings.
        window_raw = raw.get("window") or {}
        if not isinstance(window_raw, dict):
            window_raw = {}
        for f in fields(WindowConfig):
            if f.name in window_raw:
                setattr(defaults.window, f.name, window_raw[f.name])

        # Preserve unknown keys so forward compatibility is kept.
        known = {f.name for f in fields(AppConfig)}
        defaults.custom = {k: v for k, v in raw.items() if k not in known}
        return defaults

