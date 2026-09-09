"""Neumorphism dark theme: palette, font stack and global Qt style sheet.

Everything visual shares these tokens.  The "soft" neumorphic shadows used by
interactive widgets are painted manually in ``widgets.py`` (Qt's QSS does not
support ``box-shadow``), while this module supplies the shared colours and the
plain QSS used by the standard Qt widgets (combo boxes, menus, scrollbars...).
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
#  Colour palette (dark neumorphism / soft UI)
# --------------------------------------------------------------------------- #
PALETTE = {
    # page + element surfaces (all within a narrow tonal band => mono look)
    "bg":             "#2b2e33",   # window / page background
    "surface":        "#30353a",   # raised (convex) element face -> buttons
    "surface_dark":   "#26292e",   # recessed (inset) element fill
    "deep":           "#1e2125",   # darkest support colour
    # text
    "text":           "#d6dbe0",
    "text_muted":     "#8a9099",
    # accents / status
    "accent":         "#5ec8e8",   # soft cyan (primary)
    "success":        "#57d9a3",   # green  (online / RX)
    "warn":           "#e0b968",   # amber
    "danger":         "#e06c75",   # red
    "terminal_rx":    "#9cdcfe",   # incoming data
    "terminal_tx":    "#7ee787",   # echoed outgoing data
    "terminal_sys":   "#8a9099",   # system / hint lines
    # neumorphic shadow colours (RGBA)
    "shadow_light":   (255, 255, 255, 28),
    "shadow_dark":    (0, 0, 0, 110),
}

# --------------------------------------------------------------------------- #
#  Fonts
# --------------------------------------------------------------------------- #
UI_FONT      = "Segoe UI"
UI_FONT_SIZE = 10
TERM_FONT    = "Consolas"
TERM_SIZE    = 10


def lighten(c: str, amt: int = 12) -> str:
    """Return a lighter hex colour."""
    v = [int(c[i:i + 2], 16) for i in (1, 3, 5)]
    v = [min(255, x + amt) for x in v]
    return "#%02x%02x%02x" % tuple(v)


def darken(c: str, amt: int = 12) -> str:
    """Return a darker hex colour."""
    v = [int(c[i:i + 2], 16) for i in (1, 3, 5)]
    v = [max(0, x - amt) for x in v]
    return "#%02x%02x%02x" % tuple(v)


# --------------------------------------------------------------------------- #
#  Global style sheet
# --------------------------------------------------------------------------- #
def build_qss() -> str:
    """Build the global style sheet for the standard Qt widgets."""
    bgl = PALETTE["bg"]
    return """
    QWidget {
        background: transparent;
        color: %(text)s;
        selection-background-color: %(accent)s;
        selection-color: %(bg)s;
        font-family: "%(ui_font)s";
        font-size: %(ui_size)spx;
    }

    /* ---------- menu bar (native QMenuBar) ---------- */
    QMenuBar {
        background: %(bg)s;
        color: %(text_muted)s;
        padding: 2px 4px;
        border-bottom: 1px solid %(deep)s;
    }
    QMenuBar::item { background: transparent; padding: 4px 12px; border-radius: 6px; }
    QMenuBar::item:selected { background: %(surface)s; color: %(text)s; }

    QMenu {
        background: %(surface_dark)s;
        color: %(text)s;
        border: 1px solid %(deep)s;
        border-radius: 10px;
        padding: 6px;
    }
    QMenu::item { padding: 6px 22px 6px 12px; border-radius: 6px; }
    QMenu::item:selected { background: %(accent)s; color: %(bg)s; }
    QMenu::separator { height: 1px; background: %(deep)s; margin: 5px 8px; }

    /* ---------- combo boxes ---------- */
    QComboBox {
        background: %(surface_dark)s;
        color: %(text)s;
        border: 1px solid %(deep)s;
        border-radius: 9px;
        padding: 5px 12px;
        min-width: 66px;
    }
    QComboBox::drop-down { border: none; width: 22px; }
    QComboBox::down-arrow {
        image: none; width: 0; height: 0;
        border-left: 5px solid transparent;
        border-right: 5px solid transparent;
        border-top: 6px solid %(text_muted)s;
        margin-right: 4px;
    }
    QComboBox QAbstractItemView {
        background: %(surface_dark)s;
        color: %(text)s;
        border: 1px solid %(deep)s;
        border-radius: 8px;
        selection-background-color: %(accent)s;
        selection-color: %(bg)s;
        outline: 0;
    }
    QComboBox:on { border-color: %(accent)s; }

    /* ---------- text inputs ---------- */
    QLineEdit {
        background: %(surface_dark)s;
        color: %(text)s;
        border: 1px solid %(deep)s;
        border-radius: 9px;
        padding: 5px 12px;
    }
    QLineEdit:focus { border-color: %(accent)s; }

    /* ---------- terminal ---------- */
    QPlainTextEdit#terminal { background: transparent; color: %(terminal_rx)s; border: none; }

    /* ---------- scrollbars ---------- */
    QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
    QScrollBar::handle:vertical { background: %(text_muted)s; border-radius: 4px; min-height: 24px; }
    QScrollBar::handle:vertical:hover { background: %(text)s; }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }

    QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
    QScrollBar::handle:horizontal { background: %(text_muted)s; border-radius: 4px; min-width: 24px; }
    QScrollBar::handle:horizontal:hover { background: %(text)s; }
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: none; }

    /* ---------- tooltip ---------- */
    QToolTip {
        background: %(surface_dark)s;
        color: %(text)s;
        border: 1px solid %(deep)s;
        border-radius: 6px;
        padding: 4px 8px;
    }
    """ % {
        "text":        PALETTE["text"],
        "text_muted":  PALETTE["text_muted"],
        "bg":          PALETTE["bg"],
        "surface":     PALETTE["surface"],
        "surface_dark": PALETTE["surface_dark"],
        "deep":        PALETTE["deep"],
        "accent":      PALETTE["accent"],
        "terminal_rx": PALETTE["terminal_rx"],
        "ui_font":     UI_FONT,
        "ui_size":     UI_FONT_SIZE,
    }
