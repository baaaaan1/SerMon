"""Theme subsystem: design tokens, runtime QSS generation and ThemeManager.

Public API
----------
* :class:`ThemeManager` -- applies the active theme and broadcasts changes.
* :func:`get_theme_manager` -- the process-wide manager singleton.
* :class:`Theme` / :data:`DARK_THEME` / :data:`LIGHT_THEME` -- design tokens.
* :func:`render_stylesheet` / :func:`apply_palette` -- build + apply the QSS.
"""

from __future__ import annotations

from .manager import THEME_MODES, ThemeManager, get_theme_manager
from .palette import DARK_THEME, LIGHT_THEME, Theme, contrast_ratio, resolve_theme
from .qss import apply_palette, render_stylesheet

__all__ = [
    "DARK_THEME",
    "LIGHT_THEME",
    "THEME_MODES",
    "Theme",
    "ThemeManager",
    "apply_palette",
    "contrast_ratio",
    "get_theme_manager",
    "render_stylesheet",
    "resolve_theme",
]

