"""QApplication bootstrap for the Serial Monitor."""

from __future__ import annotations

import logging

from PySide6.QtWidgets import QApplication

from services.config import ConfigManager

from .bridge import SerialBridge
from .theme import get_theme_manager
from .window import MainWindow

logger = logging.getLogger(__name__)


class Application:
    """Encapsulate Qt application setup so it can be run and tested."""

    def __init__(self, config_manager: ConfigManager) -> None:
        self._config_manager = config_manager
        self._qt_app: QApplication | None = None
        self._window: MainWindow | None = None

    def run(self) -> int:
        """Create the Qt event loop, showing the main window."""
        app = QApplication.instance()
        if not isinstance(app, QApplication):
            app = QApplication([])
        self._qt_app = app
        app.setApplicationName("Serial Monitor")
        app.setOrganizationName("SerialMonitor")
        config = self._config_manager.get()

        theme_manager = get_theme_manager()
        theme_manager.apply(app, config.theme)

        bridge = SerialBridge(
            reconnect_enabled=bool(config.reconnect_enabled),
            reconnect_interval=float(config.reconnect_interval),
        )
        self._window = MainWindow(
            bridge, config=config, save=self._config_manager.save, theme_manager=theme_manager
        )
        self._window.show()
        logger.info("Main window shown")
        return app.exec()

