"""Runtime stylesheet generation from design tokens.

The application does not ship a static ``.qss`` file; instead the stylesheet is
rendered from a :class:`~app.theme.palette.Theme` on every switch.  This keeps
every colour in one place (``Theme``) and lets themes change at runtime without
restarting the process.

A ``QPalette`` is also applied for the parts Qt draws natively (menus, dialogs,
selection), which makes ``System`` mode track the OS reliably.
"""

from __future__ import annotations

from string import Template

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from .palette import TYPOGRAPHY, Theme, theme_as_dict

# -- Stylesheet parts ------------------------------------------------------------

_QSS_BASE = """
QWidget {
    background-color: $background;
    color: $text;
    font-family: $font_family;
    font-size: $font_size_base;
    selection-background-color: $selection_bg;
    selection-color: $selection_text;
}

QMainWindow, QDialog {
    background-color: $window;
}

/* ---- Toolbar ----------------------------------------------------------- */
QToolBar#mainToolbar {
    background-color: $surface_toolbar;
    border: none;
    border-bottom: 2px solid $border;
    padding: 4px 8px;
    spacing: 6px;
}
QToolBar#mainToolbar QLabel { color: $text_muted; background: transparent; }
QLabel#appTitle {
    color: $text_strong;
    font-size: $font_size_title;
    font-weight: 700;
    letter-spacing: 1px;
    padding-right: 6px;
}
QToolButton {
    background-color: transparent;
    color: $text;
    border: 1px solid transparent;
    border-radius: $radius;
    padding: 5px 10px;
}
QToolButton:hover { background-color: $surface_hover; }
QToolButton:pressed { background-color: $surface_pressed; }
QToolButton:checked {
    background-color: $surface_selected;
    border: 1px solid $accent;
    color: $accent_text;
}

/* ---- Inputs ------------------------------------------------------------ */
QComboBox, QLineEdit, QPlainTextEdit {
    background-color: $surface_input;
    border: 1px solid $border;
    border-radius: $radius;
    padding: 4px 8px;
}
QComboBox:hover, QLineEdit:hover, QPlainTextEdit:hover { border-color: $border_strong; }
QComboBox:focus, QLineEdit:focus, QPlainTextEdit:focus { border-color: $border_focus; }
QComboBox::drop-down { border: none; width: 20px; }
QComboBox::down-arrow {
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid $text_muted;
    margin-right: 4px;
}
QComboBox QAbstractItemView {
    background-color: $surface_input_alt;
    border: 1px solid $border;
    outline: none;
    selection-background-color: $surface_selected;
    selection-color: $text_strong;
}

/* ---- Checkboxes -------------------------------------------------------- */
QCheckBox { spacing: 6px; color: $text; }
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid $border_strong;
    border-radius: 4px;
    background-color: $surface_input;
}
QCheckBox::indicator:hover { border-color: $accent; }
QCheckBox::indicator:checked { background-color: $accent; border-color: $accent; }

/* ---- Terminal find bar -------------------------------------------------- */
QWidget#terminalFindBar {
    background-color: $surface_toolbar;
    border-bottom: 1px solid $border;
}
QLineEdit#terminalFindInput {
    background-color: $surface_input_alt;
    border: 1px solid $border_strong;
    border-radius: $radius;
    padding: 4px 8px;
}
QLineEdit#terminalFindInput:focus { border-color: $border_focus; }
QToolButton#terminalFindClose { color: $text_muted; }
QToolButton#terminalFindClose:hover {
    color: $text;
    background-color: $surface_hover;
}
"""


_QSS_BUTTONS = """
/* ---- Buttons ----------------------------------------------------------- */
QPushButton {
    background-color: $surface_button;
    border: 1px solid $border;
    border-radius: $radius;
    padding: 6px 14px;
    color: $text;
}
QPushButton:hover { background-color: $surface_button_hover; border-color: $border_strong; }
QPushButton:pressed { background-color: $surface_pressed; }
QPushButton:disabled { color: $text_faint; background-color: $surface_disabled; border-color: $border_disabled; }
QPushButton#sendBtn { background-color: $accent; color: $text_on_accent; font-weight: 700; border: none; }
QPushButton#sendBtn:hover { background-color: $accent_hover; }
QPushButton#sendBtn:disabled { background-color: $accent_disabled; color: $accent_disabled_text; }

/* Secondary action (Clear): a ghost button tinted with the secondary role. */
QPushButton#clearBtn {
    background-color: transparent;
    color: $secondary;
    font-weight: 600;
    border: 1px solid $border_strong;
}
QPushButton#clearBtn:hover { background-color: $surface_hover; border-color: $secondary; }
QPushButton#clearBtn:pressed { background-color: $surface_pressed; }
QPushButton#clearBtn:disabled { color: $text_faint; border-color: $border_disabled; background-color: transparent; }

/* Muted secondary (Re-send): a quiet ghost button for the last command. */
QPushButton#resendBtn {
    background-color: transparent;
    color: $text_muted;
    border: 1px solid $border_strong;
}
QPushButton#resendBtn:hover { background-color: $surface_hover; border-color: $text_muted; color: $text; }
QPushButton#resendBtn:pressed { background-color: $surface_pressed; }
QPushButton#resendBtn:disabled { color: $text_faint; border-color: $border_disabled; background-color: transparent; }

/* Connect / disconnect state (driven by the "connected" dynamic property). */
QPushButton#connectBtn {
    background-color: $accent;
    color: $text_on_accent;
    font-weight: 700;
    border: none;
    padding: 8px 14px;
}
QPushButton#connectBtn:hover { background-color: $accent_hover; }
QPushButton#connectBtn[connected="true"] { background-color: $success; color: $text_on_accent; }
QPushButton#connectBtn[connected="false"] { background-color: $accent; color: $text_on_accent; }

/* ---- Group box --------------------------------------------------------- */
QGroupBox#configGroup {
    border: 1px solid $border;
    border-radius: $radius_group;
    margin-top: 10px;
    padding-top: 8px;
    background-color: $surface;
}
QGroupBox#configGroup::title {
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 4px;
    color: $text_muted;
    font-weight: 600;
}

/* ---- Sidebar / panels -------------------------------------------------- */
QWidget#sidebar {
    background-color: $surface_sidebar;
    border-right: 2px solid $border;
}
QWidget#terminalHolder { background-color: $background; }
QLabel#sectionTitle {
    color: $text_muted;
    font-size: $font_size_small;
    font-weight: 700;
    letter-spacing: 1px;
}

/* ---- Splitter ---------------------------------------------------------- */
QSplitter::handle { background-color: $border; }
QSplitter::handle:hover { background-color: $accent; }
QSplitter::handle:horizontal { width: 4px; }
"""


_QSS_MISC = """
/* ---- Terminal ---------------------------------------------------------- */
QTextEdit {
    background-color: $terminal_bg;
    border: 1px solid $border;
    border-radius: $radius_group;
    color: $terminal_text;
    font-family: $font_mono;
    font-size: $font_size_terminal;
    padding: 6px;
}

/* ---- Scrollbars -------------------------------------------------------- */
QScrollBar:vertical { background: $scrollbar_bg; width: 12px; margin: 0; }
QScrollBar::handle:vertical {
    background: $scrollbar_handle;
    min-height: 24px;
    border-radius: $radius;
}
QScrollBar::handle:vertical:hover { background: $accent; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { background: $scrollbar_bg; height: 12px; margin: 0; }
QScrollBar::handle:horizontal {
    background: $scrollbar_handle;
    min-width: 24px;
    border-radius: $radius;
}
QScrollBar::handle:horizontal:hover { background: $accent; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

/* ---- Quick-commands list ---------------------------------------------- */
QListWidget {
    background-color: $surface_list;
    border: 1px solid $border;
    border-radius: $radius;
    padding: 4px;
}
QListWidget::item { padding: 6px 8px; border-radius: 4px; color: $text; }
QListWidget::item:hover { background-color: $surface_hover; }
QListWidget::item:selected { background-color: $surface_selected; color: $accent_text; }

/* ---- Status bar -------------------------------------------------------- */
QStatusBar {
    background-color: $surface_status;
    border-top: 2px solid $border;
    color: $text_muted;
}
QStatusBar::item { border: none; }
QLabel#statusMessage { color: $text_muted; background: transparent; }
QLabel#lineState { color: $accent; background: transparent; font-weight: 600; }

/* ---- Tooltips ---------------------------------------------------------- */
QToolTip {
    background-color: $tooltip_bg;
    color: $tooltip_text;
    border: 1px solid $tooltip_border;
    padding: 6px;
    border-radius: 4px;
}
"""

#: The complete stylesheet template with ``$token`` placeholders.
QSS_TEMPLATE: str = _QSS_BASE + _QSS_BUTTONS + _QSS_MISC


def render_stylesheet(theme: Theme) -> str:
    """Return a complete stylesheet string for *theme*.

    The stylesheet is produced by substituting every ``$token`` placeholder in
    :data:`QSS_TEMPLATE` with the matching palette / typography token.
    """
    tokens = {**theme_as_dict(theme), **TYPOGRAPHY}
    return Template(QSS_TEMPLATE).safe_substitute(tokens)


def apply_palette(app: QApplication, theme: Theme) -> None:
    """Set a :class:`QPalette` on *app* derived from *theme*.

    The stylesheet styles most widgets, but Qt still paints a few native parts
    (menus, dialogs, selection, tooltips).  Setting a matching palette keeps the
    whole application consistent and lets ``System`` mode follow the OS without
    leaving grey native widgets behind.
    """
    palette = QPalette()

    def role_set(role: QPalette.ColorRole, hex_color: str) -> None:
        palette.setColor(role, QColor(hex_color))

    role_set(QPalette.ColorRole.Window, theme.window)
    role_set(QPalette.ColorRole.WindowText, theme.text)
    role_set(QPalette.ColorRole.Base, theme.surface_input)
    role_set(QPalette.ColorRole.AlternateBase, theme.surface_input_alt)
    role_set(QPalette.ColorRole.Text, theme.text)
    role_set(QPalette.ColorRole.Button, theme.surface_button)
    role_set(QPalette.ColorRole.ButtonText, theme.text)
    role_set(QPalette.ColorRole.Highlight, theme.selection_bg)
    role_set(QPalette.ColorRole.HighlightedText, theme.selection_text)
    role_set(QPalette.ColorRole.Link, theme.accent)
    role_set(QPalette.ColorRole.ToolTipBase, theme.tooltip_bg)
    role_set(QPalette.ColorRole.ToolTipText, theme.tooltip_text)
    role_set(QPalette.ColorRole.PlaceholderText, theme.text_faint)

    for disabled_role in (
        QPalette.ColorRole.Text,
        QPalette.ColorRole.ButtonText,
        QPalette.ColorRole.WindowText,
    ):
        palette.setColor(QPalette.ColorGroup.Disabled, disabled_role, QColor(theme.text_faint))

    app.setPalette(palette)



