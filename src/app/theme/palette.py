"""Design-token palettes for the Serial Monitor themes.

Every colour in the application derives from a single :class:`Theme`.  The
stylesheets are *generated* from these tokens (see :mod:`app.theme.qss`), and
widgets that paint colour in Python read from the active theme through
:class:`~app.theme.manager.ThemeManager`.  This keeps colours in one place so a
theme (or, in the future, a custom accent) can be introduced without editing
individual widgets or stylesheet files.

Theme-invariant typography/geometry constants live here too and are interpolated
into the generated stylesheet.

Semantic colour roles
---------------------
Roles describe *meaning*, not a raw hue, so widgets and the stylesheet reference
intent.  The mapping used across the app is:

* ``accent``   -- Primary / interactive highlight (Connect, Send, selection).
* ``secondary``-- Secondary / supporting tint (less prominent actions).
* ``success`` / ``connected``  -- Positive / connected state (green).
* ``warning``  -- In-progress / caution (amber).
* ``error``    -- Failure / faulty state (vivid red).
* ``disconnected`` -- Idle/offline state (muted red, distinct from ``error``).
* ``info`` / ``rx``  -- Information / data in (blue).
* ``tx``       -- Data out / user action (purple).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, fields, replace
from typing import Any

#: A hex colour of the form ``#rrggbb`` or ``#rrggbbaa``.
_HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}(?:[0-9a-fA-F]{2})?$")

#: Theme-invariant typography / geometry tokens (shared by both palettes).
TYPOGRAPHY: dict[str, str] = {
    "font_family": '"Segoe UI", "Noto Sans", sans-serif',
    "font_mono": '"Cascadia Code", "Consolas", "Courier New", monospace',
    "font_size_base": "10pt",
    "font_size_small": "9pt",
    "font_size_title": "12pt",
    "font_size_terminal": "11pt",
    "radius": "6px",
    "radius_group": "8px",
}


@dataclass(frozen=True)
class Theme:
    """A complete set of semantic colour tokens for one resolved theme.

    Colour roles are kept deliberately semantic (``accent``, ``surface``,
    ``success``, ``terminal_bg``, ...) rather than describing a specific hex, so
    widgets and the stylesheet both reference intent instead of raw values.
    """

    name: str

    # -- Surfaces -------------------------------------------------------------
    background: str
    window: str
    surface: str
    surface_toolbar: str
    surface_sidebar: str
    surface_status: str
    surface_input: str
    surface_input_alt: str
    surface_list: str
    surface_button: str
    surface_button_hover: str
    surface_hover: str
    surface_pressed: str
    surface_disabled: str
    surface_selected: str

    # -- Lines / borders ------------------------------------------------------
    border: str
    border_strong: str
    border_disabled: str
    border_focus: str

    # -- Text ----------------------------------------------------------------
    text: str
    text_strong: str
    text_muted: str
    text_faint: str
    text_on_accent: str
    accent_text: str

    # -- Brand / secondary ----------------------------------------------------
    secondary: str

    # -- Accent (single customisation point) ----------------------------------
    accent: str
    accent_hover: str
    accent_disabled: str
    accent_disabled_text: str

    # -- Semantic status ------------------------------------------------------
    success: str
    warning: str
    error: str
    info: str
    connected: str
    disconnected: str

    # -- Terminal -------------------------------------------------------------
    terminal_bg: str
    terminal_text: str
    marker_connected: str
    marker_eof: str

    # -- Activity / misc ------------------------------------------------------
    rx: str
    tx: str
    blip_dim: str
    scrollbar_bg: str
    scrollbar_handle: str
    tooltip_bg: str
    tooltip_text: str
    tooltip_border: str
    selection_bg: str
    selection_text: str

    def with_accent(self, accent: str) -> Theme:
        """Return a copy of this palette with a custom accent hue.

        ``accent`` is the base accent colour; the hover / disabled / text-on-accent
        tokens are derived so a custom accent stays internally consistent without
        having to specify every accent variant by hand.
        """
        return replace(
            self,
            accent=accent,
            accent_hover=_darken_hex(accent, 0.12),
            accent_disabled=_mix_hex(accent, self.window, 0.62),
            accent_disabled_text=_mix_hex(accent, self.text, 0.35),
            border_focus=accent,
            selection_bg=accent,
            selection_text=_contrast_hex(accent),
        )

    def validate(self) -> None:
        """Raise ``ValueError`` if any colour token is not a valid hex colour."""
        for f in fields(self):
            if f.name == "name":
                continue
            value = getattr(self, f.name)
            if not isinstance(value, str) or not _HEX_COLOR.match(value):
                raise ValueError(f"Theme.{f.name!r} is not a valid hex colour: {value!r}")


#: Built-in dark palette (default look of the application).
DARK_THEME: Theme = Theme(
    name="dark",
    background="#14151f",
    window="#14151f",
    surface="#1a1d2a",
    surface_toolbar="#1b1d2b",
    surface_sidebar="#171926",
    surface_status="#10121b",
    surface_input="#1f2333",
    surface_input_alt="#1c1f2e",
    surface_list="#1b1e2c",
    surface_button="#2b2e40",
    surface_button_hover="#353948",
    surface_hover="#262940",
    surface_pressed="#22242f",
    surface_disabled="#20222e",
    surface_selected="#2a3350",
    border="#34374f",
    border_strong="#4c5470",
    border_disabled="#262940",
    border_focus="#4cc9f0",
    text="#e6e8f0",
    text_strong="#ffffff",
    text_muted="#8b8fa8",
    text_faint="#5a5d75",
    text_on_accent="#0b0c12",
    accent_text="#7fd3ff",
    secondary="#9aa1c0",
    accent="#4cc9f0",
    accent_hover="#63d3f5",
    accent_disabled="#33506b",
    accent_disabled_text="#9ab8cf",
    success="#3ddc84",
    warning="#ffb703",
    error="#ef476f",
    info="#4cc9f0",
    connected="#3ddc84",
    disconnected="#c56d7e",
    terminal_bg="#0e0f16",
    terminal_text="#d5f0ff",
    marker_connected="#3ddc84",
    marker_eof="#4cc9f0",
    rx="#4cc9f0",
    tx="#b57aff",
    blip_dim="#5a5d75",
    scrollbar_bg="#12141d",
    scrollbar_handle="#34374f",
    tooltip_bg="#1c1f2e",
    tooltip_text="#e6e8f0",
    tooltip_border="#4c5470",
    selection_bg="#4cc9f0",
    selection_text="#0b0c12",
)


#: Built-in light palette (bright, high-contrast, soft panels).
LIGHT_THEME: Theme = Theme(
    name="light",
    background="#f4f6fb",
    window="#f4f6fb",
    surface="#ffffff",
    surface_toolbar="#eef1f8",
    surface_sidebar="#ffffff",
    surface_status="#e6eaf3",
    surface_input="#ffffff",
    surface_input_alt="#eef1f8",
    surface_list="#ffffff",
    surface_button="#ffffff",
    surface_button_hover="#e9edf6",
    surface_hover="#e4e9f4",
    surface_pressed="#d7dceb",
    surface_disabled="#f0f2f8",
    surface_selected="#d9e8fb",
    border="#d3d8e6",
    border_strong="#aab2c7",
    border_disabled="#e1e5f0",
    border_focus="#0086d1",
    text="#1c202b",
    text_strong="#11141b",
    text_muted="#5c6472",
    text_faint="#98a0b0",
    text_on_accent="#ffffff",
    accent_text="#0069ad",
    secondary="#5c6472",
    accent="#0086d1",
    accent_hover="#0d9ce6",
    accent_disabled="#a8c9de",
    accent_disabled_text="#3d6d95",
    success="#1e7a2e",
    warning="#a56600",
    error="#c0284a",
    info="#0069ad",
    connected="#1e7a2e",
    disconnected="#b04a60",
    terminal_bg="#fbfcfe",
    terminal_text="#1c202b",
    marker_connected="#1e7a2e",
    marker_eof="#0069ad",
    rx="#0069ad",
    tx="#6d28d9",
    blip_dim="#98a0b0",
    scrollbar_bg="#e6eaf3",
    scrollbar_handle="#b9c0d2",
    tooltip_bg="#ffffff",
    tooltip_text="#1c202b",
    tooltip_border="#b9c0d2",
    selection_bg="#0086d1",
    selection_text="#ffffff",
)


#: Only built-in resolved themes; custom accents go through :meth:`Theme.with_accent`.
THEMES: dict[str, Theme] = {"light": LIGHT_THEME, "dark": DARK_THEME}


def resolve_theme(mode: str, accent: str | None = None) -> Theme:
    """Return the built-in :class:`Theme` for *mode* (``"light"`` / ``"dark"``).

    Unknown modes fall back to the dark palette.  When *accent* is provided the
    palette is derived from it via :meth:`Theme.with_accent`, which is how a
    future custom accent preference plugs in without touching any widget.
    """
    theme = THEMES.get(mode, DARK_THEME)
    if accent:
        theme = theme.with_accent(accent)
    return theme


# -- Colour helpers (used for accent derivation) --------------------------------

#: A raw RGB triple; components may still be floating-point (e.g. after blending
#: in :func:`_mix_hex` / :func:`_darken_hex`) and are rounded by ``_clamp_byte``.
_RGBTuple = tuple[int | float, int | float, int | float]


def _clamp_byte(value: float) -> int:
    return max(0, min(255, round(value)))


def _to_rgb(hex_color: str) -> tuple[int, int, int]:
    value = hex_color.lstrip("#")
    if len(value) == 3:  # shorthand not used, but be defensive
        value = "".join(ch * 2 for ch in value)
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def _to_hex(rgb: _RGBTuple) -> str:
    r, g, b = (_clamp_byte(c) for c in rgb)
    return f"#{r:02x}{g:02x}{b:02x}"


def _darken_hex(hex_color: str, amount: float) -> str:
    """Return *hex_color* darkened by ``amount`` (0..1) toward black."""
    r, g, b = _to_rgb(hex_color)
    return _to_hex((r * (1 - amount), g * (1 - amount), b * (1 - amount)))


def _mix_hex(a: str, b: str, weight_b: float) -> str:
    """Blend ``a`` and ``b``, weighted to ``b`` by ``weight_b`` (0..1)."""
    ra, ga, ba = _to_rgb(a)
    rb, gb, bb = _to_rgb(b)
    wb = _clamp_byte(weight_b * 255) / 255.0
    return _to_hex(
        (ra * (1 - wb) + rb * wb, ga * (1 - wb) + gb * wb, ba * (1 - wb) + bb * wb)
    )


def _contrast_hex(hex_color: str) -> str:
    """Return black/white text colour with the best contrast on *hex_color*."""
    r, g, b = _to_rgb(hex_color)
    # WCAG-style relative luminance estimate.
    luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return "#000000" if luminance > 165 else "#ffffff"


def _linearize(channel: float) -> float:
    """Convert an sRGB channel (0..255) to linear-light (0..1)."""
    c = channel / 255.0
    if c <= 0.04045:
        return c / 12.92
    return ((c + 0.055) / 1.055) ** 2.4


def _relative_luminance(hex_color: str) -> float:
    """Return the WCAG relative luminance (0..1) of *hex_color*."""
    r, g, b = (_linearize(v) for v in _to_rgb(hex_color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a: str, b: str) -> float:
    """Return the WCAG contrast ratio (1..21) between two hex colours."""
    la, lb = _relative_luminance(a), _relative_luminance(b)
    lighter, darker = max(la, lb), min(la, lb)
    return (lighter + 0.05) / (darker + 0.05)


def theme_as_dict(theme: Theme) -> dict[str, Any]:
    """Return a mapping of this theme's colour tokens (used for stylesheet interpolation)."""
    return {f.name: getattr(theme, f.name) for f in fields(theme) if f.name != "name"}



