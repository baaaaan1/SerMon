"""Serial Monitor application entry point.

Run from the project root:

    python src/main.py

or, after an editable install (``pip install -e .``):

    serial-monitor
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure the ``src`` directory is on ``sys.path`` regardless of how the script
# is invoked (``python src/main.py`` or ``python -m src.main``).
_SRC = Path(__file__).resolve().parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from app.application import Application
from services.config import ConfigManager
from services.logger import configure_logging, get_logger


def main() -> int:
    """Bootstrap configuration, logging and the Qt application."""
    config_manager = ConfigManager()
    configure_logging(config_manager.get())
    logger = get_logger("main")
    logger.info("Starting Serial Monitor")

    try:
        application = Application(config_manager)
        return application.run()
    except Exception:
        logger.exception("Fatal error during startup")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
