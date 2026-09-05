"""ThemeManager: owns the active theme and applies it at runtime.

The manager tracks the user's *resolution* (Light / Dark / System), resolves
``System`` to the operating system preference (via :func:`QGuiApplication.styleHints`),
and applies the resulting :class:`~app.theme.palette.Theme` by setting the app
stylesheet and palette.  It emits :attr:`ThemeManager.theme_changed` so widgets
that paint colours directly (e.g. the terminal status dots) can repaint.

The manager is intentionally independent of the config layer -- the caller decides
when to persist the resolution; it only exposes state and emits change signals.
"""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication

from .palette import DARK_THEME, Theme, resolve_theme
from .qss import apply_palette, render_stylesheet

logger = logging.getLogger(__name__)

#: Valid theme resolutions.
THEME_MODES: tuple[str, ...] = ("light", "dark", "system")
#: Fallback resolution when an unknown / invalid value is supplied.
DEFAULT_RESOLUTION: str = "system"


class ThemeManager(QObject):
    """Applies and broadcasts the current theme.

    Attributes
    ----------
    resolution:
        The user's choice: ``"light"``, ``"dark"`` or ``"system"``.
    mode:
        The resolved theme: ``"light"`` or ``"dark"`` (System is expanded here).
    theme:
        The active :class:`Theme` palette.
    """

    #: Emitted with the resolved :class:`Theme` whenever the theme changes.
    theme_changed = Signal(object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._resolution = DEFAULT_RESOLUTION
        self._mode = "dark"
        self._theme: Theme = DARK_THEME
        self._qapp: QApplication | None = None
        self._watching_os = False

    # -- Properties ----------------------------------------------------------
    @property
    def resolution(self) -> str:
        """The user-selected resolution (``"light"`` / ``"dark"`` / ``"system"``)."""
        return self._resolution

    @property
    def mode(self) -> str:
        """The resolved mode (``"light"`` / ``"dark"``)."""
        return self._mode

    @property
    def theme(self) -> Theme:
        """The active :class:`Theme` palette."""
        return self._theme

    @property
    def application(self) -> QApplication | None:
        """The application this manager is applying to, if any."""
        return self._qapp

    # -- Public API ----------------------------------------------------------
    def apply(self, qapp: QApplication, resolution: str | None = None) -> None:
        """Attach to *qapp* and apply *resolution* (or the last one)."""
        self._qapp = qapp
        if resolution is not None:
            self._resolution = self._normalize(resolution)
        self._sync()
        self._ensure_os_watch()

    def set_resolution(self, resolution: str) -> None:
        """Switch to *resolution* and immediately apply it."""
        self._resolution = self._normalize(resolution)
        self._sync()

    # -- Internals -----------------------------------------------------------
    def _sync(self) -> None:
        self._mode = self._resolve_mode(self._resolution)
        self._theme = resolve_theme(self._mode)
        if self._qapp is not None:
            self._qapp.setStyleSheet(render_stylesheet(self._theme))
            apply_palette(self._qapp, self._theme)
        self.theme_changed.emit(self._theme)

    def _resolve_mode(self, resolution: str) -> str:
        if resolution == "system":
            return self._system_mode()
        if resolution == "light":
            return "light"
        return "dark"

    def _system_mode(self) -> str:
        hints = QGuiApplication.styleHints()
        scheme = hints.colorScheme()
        if scheme in (Qt.ColorScheme.Dark, Qt.ColorScheme.Light):
            return "dark" if scheme == Qt.ColorScheme.Dark else "light"
        # Unknown scheme -> use the active palette's luminance as a fallback.
        palette = (self._qapp or QGuiApplication).palette()
        darkness = palette.color(QPalette.ColorRole.Window).lightness() < 128
        return "dark" if darkness else "light"

    def _normalize(self, resolution: str) -> str:
        value = (resolution or "").strip().lower()
        if value not in THEME_MODES:
            logger.warning("Unknown theme resolution %r; using %r", resolution, DEFAULT_RESOLUTION)
            value = DEFAULT_RESOLUTION
        return value

    def _ensure_os_watch(self) -> None:
        """Subscribe to OS colour-scheme changes once (System mode reacts live)."""
        if self._watching_os:
            return
        hints = QGuiApplication.styleHints()
        if hasattr(type(hints), "colorSchemeChanged"):
            hints.colorSchemeChanged.connect(self._on_os_changed)
            self._watching_os = True

    def _on_os_changed(self, _scheme: Qt.ColorScheme) -> None:
        if self._resolution == "system":
            self._sync()
            logger.info("System colour scheme changed -> resolved theme: %s", self._mode)


# -- Module-level accessor ------------------------------------------------------

_manager: ThemeManager | None = None


def get_theme_manager() -> ThemeManager:
    """Return the process-wide :class:`ThemeManager` singleton.

    Widgets should use this to read the active theme and to subscribe to
    :attr:`ThemeManager.theme_changed`.  It is created lazily so importing it
    never requires a QApplication.
    """
    global _manager
    if _manager is None:
        _manager = ThemeManager()
    return _manager
