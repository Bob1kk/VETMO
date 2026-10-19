"""QSS-темы VETMO: THEME_DARK / THEME_LIGHT — строки стилей, без внешних файлов.

Требование T-020/NFR-007: всё стилевое оформление в коде Python,
чтобы PyInstaller собирал один .exe без внешних ресурсов.
"""

from string import Template

__all__ = ["THEME_DARK", "THEME_LIGHT", "theme_for"]


_DARK: dict[str, str] = {
    "bg": "#1E1F26",
    "bg_alt": "#232429",
    "panel": "#26282f",
    "panel_2": "#2C2F39",
    "text": "#E6E8EE",
    "muted": "#9AA0AC",
    "border": "#343846",
    "accent": "#5B8DEF",
    "accent_hover": "#6E9CF2",
    "accent_pressed": "#4A78D8",
    "on_accent": "#FFFFFF",
    "danger": "#E05661",
    "ok": "#3FB68B",
    "input": "#1E2028",
    "scroll": "#3A3E4B",
    "overlay_panel": "rgba(30, 31, 38, 228)",
    "overlay_title": "#C9CFDC",
    "shadow": "rgba(0, 0, 0, 120)",
}

_LIGHT: dict[str, str] = {
    "bg": "#F2F4F8",
    "bg_alt": "#EAEDF2",
    "panel": "#FFFFFF",
    "panel_2": "#EEF1F5",
    "text": "#1F2430",
    "muted": "#6B7280",
    "border": "#D5D9E2",
    "accent": "#5B8DEF",
    "accent_hover": "#4A78D8",
    "accent_pressed": "#3E68C4",
    "on_accent": "#FFFFFF",
    "danger": "#D64550",
    "ok": "#2E9C77",
    "input": "#FFFFFF",
    "scroll": "#C3C8D4",
    "overlay_panel": "rgba(255, 255, 255, 240)",
    "overlay_title": "#3A4150",
    "shadow": "rgba(0, 0, 0, 40)",
}

_TEMPLATE = Template(
    """
/* ---------- База ---------- */
QWidget {
    background: $bg;
    color: $text;
    font-family: 'Segoe UI', 'Arial', sans-serif;
    font-size: 13px;
}
QMainWindow, QDialog {
    background: $bg;
}
QWidget:disabled {
    color: $muted;
}

/* ---------- Заголовки и бейджи ---------- */
QLabel#h1 { font-size: 20px; font-weight: 700; }
QLabel#h2 { font-size: 15px; font-weight: 600; }
QLabel#muted { color: $muted; font-size: 12px; }
QLabel#mutedSmall { color: $muted; font-size: 11px; }
QLabel#badgeOnline {
    background: $ok; color: #FFFFFF; border-radius: 8px;
    padding: 2px 10px; font-size: 11px; font-weight: 600;
}
QLabel#badgeOffline {
    background: $danger; color: #FFFFFF; border-radius: 8px;
    padding: 2px 10px; font-size: 11px; font-weight: 600;
}

/* ---------- Панели и карточки ---------- */
QFrame#panel {
    background: $panel;
    border: 1px solid $border;
    border-radius: 10px;
}
QFrame#heroCard {
    background: $panel;
    border: 1px solid $border;
    border-radius: 10px;
}
QFrame#heroCard:hover {
    border: 1px solid $accent;
}
QLabel#cardName { font-size: 12px; font-weight: 600; }
QLabel#cardReason { color: $accent; font-size: 11px; }
QLabel#cardWr { color: $ok; font-size: 11px; font-weight: 600; }
QLabel#cardEmpty { color: $muted; font-size: 11px; font-style: italic; }
QLabel#iconPlaceholder {
    border-radius: 17px;
    background: $panel_2;
    color: $muted;
    font-size: 12px;
    font-weight: 700;
}

/* ---------- Кнопки ---------- */
QPushButton {
    background: $panel_2;
    border: 1px solid $border;
    border-radius: 8px;
    padding: 6px 14px;
    color: $text;
}
QPushButton:hover {
    background: $bg_alt;
    border: 1px solid $accent;
}
QPushButton:pressed {
    background: $accent_pressed;
    border: 1px solid $accent_pressed;
    color: $on_accent;
}
QPushButton:disabled {
    background: $panel_2;
    border: 1px solid $border;
    color: $muted;
}
QPushButton#primary {
    background: $accent;
    border: 1px solid $accent;
    color: $on_accent;
    font-weight: 700;
}
QPushButton#primary:hover {
    background: $accent_hover;
    border: 1px solid $accent_hover;
}
QPushButton#primary:pressed {
    background: $accent_pressed;
}
QPushButton#primary:disabled {
    background: $accent_pressed;
    color: rgba(255, 255, 255, 140);
}
QPushButton#bigOverlay {
    background: $accent;
    border: 1px solid $accent;
    color: $on_accent;
    border-radius: 10px;
    font-size: 15px;
    font-weight: 700;
    padding: 12px 22px;
}
QPushButton#bigOverlay:hover { background: $accent_hover; }
QPushButton#bigOverlay:pressed { background: $accent_pressed; }
QPushButton#bigOverlay:disabled {
    background: $accent_pressed;
    color: rgba(255, 255, 255, 140);
}
QPushButton#secondary {
    background: transparent;
    border: 1px solid $border;
    color: $muted;
}
QPushButton#secondary:hover {
    border: 1px solid $accent;
    color: $text;
}

/* ---------- Поля ввода ---------- */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background: $input;
    border: 1px solid $border;
    border-radius: 8px;
    padding: 4px 8px;
    selection-background-color: $accent;
    selection-color: $on_accent;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
    border: 1px solid $accent;
}
QComboBox::drop-down {
    border: none;
    width: 20px;
}
QComboBox::down-arrow {
    width: 0px;
    height: 0px;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid $muted;
    margin-right: 6px;
}
QComboBox QAbstractItemView {
    background: $panel_2;
    border: 1px solid $border;
    selection-background-color: $accent;
    selection-color: $on_accent;
    outline: none;
}
QSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::up-button,
QDoubleSpinBox::down-button {
    background: $panel_2;
    border: 1px solid $border;
    border-radius: 3px;
    width: 14px;
}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-bottom: 5px solid $muted;
}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid $muted;
}

/* ---------- Чекбоксы ---------- */
QCheckBox { spacing: 8px; background: transparent; }
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid $border;
    border-radius: 4px;
    background: $input;
}
QCheckBox::indicator:hover { border: 1px solid $accent; }
QCheckBox::indicator:checked {
    background: $accent;
    border: 1px solid $accent;
    image: none;
}

/* ---------- Слайдер ---------- */
QSlider::groove:horizontal {
    height: 6px;
    background: $input;
    border: 1px solid $border;
    border-radius: 3px;
}
QSlider::sub-page:horizontal {
    background: $accent;
    border-radius: 3px;
}
QSlider::handle:horizontal {
    background: $accent;
    width: 16px;
    height: 16px;
    margin: -6px 0;
    border-radius: 8px;
    border: 2px solid $bg;
}
QSlider::handle:horizontal:hover { background: $accent_hover; }

/* ---------- Таблицы и списки ---------- */
QTableWidget {
    background: $panel;
    alternate-background-color: $panel_2;
    border: none;
    gridline-color: transparent;
    selection-background-color: $accent;
    selection-color: $on_accent;
}
QTableCornerButton::section { background: $panel; border: none; }
QHeaderView::section {
    background: $panel_2;
    color: $muted;
    border: none;
    border-bottom: 1px solid $border;
    padding: 6px 8px;
    font-size: 12px;
    font-weight: 600;
}
QListWidget {
    background: $panel;
    border: 1px solid $border;
    border-radius: 8px;
    padding: 4px;
    outline: none;
}
QListWidget::item {
    border-radius: 6px;
    padding: 4px 8px;
}
QListWidget::item:hover { background: $panel_2; }
QListWidget::item:selected {
    background: $accent;
    color: $on_accent;
}

/* ---------- Скроллбары ---------- */
QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: $scroll;
    border-radius: 5px;
    min-height: 30px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
QScrollBar:horizontal {
    background: transparent;
    height: 10px;
    margin: 0;
}
QScrollBar::handle:horizontal {
    background: $scroll;
    border-radius: 5px;
    min-width: 30px;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: none; }

/* ---------- Статусбар, тултипы, меню ---------- */
QStatusBar {
    background: $panel;
    color: $muted;
    border-top: 1px solid $border;
}
QStatusBar::item { border: none; }
QToolTip {
    background: $panel_2;
    color: $text;
    border: 1px solid $border;
    border-radius: 6px;
    padding: 4px 8px;
}
QMenu {
    background: $panel_2;
    border: 1px solid $border;
    border-radius: 8px;
    padding: 4px;
}
QMenu::item {
    padding: 6px 20px;
    border-radius: 6px;
}
QMenu::item:selected {
    background: $accent;
    color: $on_accent;
}
QProgressBar {
    background: $panel_2;
    border: 1px solid $border;
    border-radius: 6px;
    text-align: center;
    color: $muted;
}
QProgressBar::chunk {
    background: $accent;
    border-radius: 6px;
}

/* ---------- Оверлей (полупрозрачные панели поверх игры) ---------- */
QWidget#overlayRoot { background: transparent; }
QFrame#overlayPanel {
    background: $overlay_panel;
    border: 1px solid $border;
    border-radius: 12px;
}
QLabel#overlayTitle {
    color: $overlay_title;
    font-size: 13px;
    font-weight: 700;
}
QLabel#overlayStep {
    color: $accent;
    font-size: 12px;
    font-weight: 600;
}
QFrame#overlayCard {
    background: $overlay_panel;
    border: 1px solid $border;
    border-radius: 8px;
}
QFrame#overlayCard:hover { border: 1px solid $accent; }
QLabel#overlayCardName { color: $text; font-size: 11px; font-weight: 600; }
QLabel#overlayCardReason { color: $accent; font-size: 10px; }
QLabel#overlayCardWr { color: $ok; font-size: 10px; font-weight: 600; }
QLabel#overlayCardEmpty { color: $muted; font-size: 10px; font-style: italic; }
QLabel#overlayPosLabel { color: $muted; font-size: 10px; font-weight: 600; }
""".lstrip()
)


def _render(palette: dict[str, str]) -> str:
    """Собирает QSS из палитры (без единого пустого блока {})."""
    return _TEMPLATE.substitute(palette)


THEME_DARK: str = _render(_DARK)
THEME_LIGHT: str = _render(_LIGHT)


def theme_for(name: str) -> str:
    """'light' -> светлая тема, иначе тёмная (значение по умолчанию)."""
    return THEME_LIGHT if name == "light" else THEME_DARK
