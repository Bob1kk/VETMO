"""QSS-темы VETMO: THEME_DARK / THEME_LIGHT (R2, задача D — свежий рестайл).

R2-штрихи: градиентные главные кнопки, чипсы-фильтры с активной заливкой
акцентом, мягкие тени карточек (эффекты в widgets-коде), hover-состояния
всем интерактивным, секционные заголовки («📰 НОВОСТИ ПАТЧЕЙ», «⚙ …»),
компактная мета-таблица без сетки. Всё QSS — темы в Python-коде (T-020:
PyInstaller .exe не теряет стили).
"""

from string import Template

__all__ = ["THEME_DARK", "THEME_LIGHT", "theme_for"]


_DARK: dict[str, str] = {
    "bg": "#181A20",
    "bg_alt": "#1E2027",
    "panel": "#22242C",
    "panel_2": "#282B34",
    "text": "#E8EAF0",
    "muted": "#9AA0AC",
    "border": "#32364A",
    "accent": "#5B8DEF",
    "accent_hover": "#6E9CF2",
    "accent_pressed": "#4A78D8",
    "on_accent": "#FFFFFF",
    "danger": "#E05661",
    "ok": "#3FB68B",
    "input": "#1B1D24",
    "scroll": "#3A3E4B",
    "overlay_panel": "rgba(24, 26, 32, 228)",
    "overlay_title": "#C9CFDC",
    "shadow": "rgba(0, 0, 0, 120)",
}

_LIGHT: dict[str, str] = {
    "bg": "#F3F5F9",
    "bg_alt": "#EAEDF3",
    "panel": "#FFFFFF",
    "panel_2": "#EEF1F6",
    "text": "#1F2430",
    "muted": "#657086",
    "border": "#D5D9E2",
    "accent": "#4A78D8",
    "accent_hover": "#5B8DEF",
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
/* ---------- база ---------- */
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

/* ---------- слои заголовков/бейджи ---------- */
QLabel#h1 { font-size: 19px; font-weight: 700; }
QLabel#h2 { font-size: 14px; font-weight: 600; }
QLabel#sectionTitle {
    font-size: 11px;
    font-weight: 700;
    color: $muted;
    letter-spacing: 1px;
    background: transparent;
    padding: 2px 2px;
}
QLabel#sectionLabel {
    font-size: 11px;
    font-weight: 700;
    color: $muted;
    letter-spacing: 0.6px;
    background: transparent;
}
QLabel#chipLabel {
    font-size: 11px;
    font-weight: 600;
    color: $muted;
    background: transparent;
    padding-right: 4px;
}
QLabel#muted { color: $muted; font-size: 12px; background: transparent; }
QLabel#mutedSmall { color: $muted; font-size: 11px; background: transparent; }
QLabel#delta {
    font-size: 12px;
    font-weight: 700;
    background: transparent;
}
QLabel#nodata { color: $muted; font-size: 12px; background: transparent; }
QLabel#metaHeroName {
    font-size: 13px;
    font-weight: 600;
    background: transparent;
}
QLabel#metaRate {
    font-size: 12px;
    font-weight: 600;
    background: transparent;
}
QLabel#newsTitle {
    color: $accent;
    font-size: 13px;
    font-weight: 600;
    background: transparent;
}
QLabel#newsTitle:hover { text-decoration: underline; }
QLabel#newsSnippet {
    color: $muted;
    font-size: 12px;
    background: transparent;
}
QLabel#newsPlaceholder {
    color: $muted;
    font-size: 12px;
    padding: 8px 6px;
    background: transparent;
}
QLabel#badgeOnline {
    background: $ok; color: #FFFFFF; border-radius: 8px;
    padding: 2px 10px; font-size: 11px; font-weight: 600;
}
QLabel#badgeOffline {
    background: $danger; color: #FFFFFF; border-radius: 8px;
    padding: 2px 10px; font-size: 11px; font-weight: 600;
}

/* ---------- панели и карточки ---------- */
QFrame#panel {
    background: $panel;
    border: 1px solid $border;
    border-radius: 12px;
}
QFrame#metaToolbar {
    background: $panel_2;
    border: 1px solid $border;
    border-radius: 10px;
}
QFrame#newsList, QFrame#newsScroll { background: transparent; border: none; }
QFrame#newsRow {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 8px;
}
QFrame#newsRow:hover {
    background: $panel_2;
    border: 1px solid $border;
}
QFrame#heroCard {
    background: $panel;
    border: 1px solid $border;
    border-radius: 12px;
}
QFrame#heroCard:hover {
    border: 1px solid $accent;
}
QLabel#cardName { font-size: 12px; font-weight: 600; }
QLabel#cardReason { color: $accent; font-size: 11px; background: transparent; }
QLabel#cardWr { color: $ok; font-size: 11px; font-weight: 600; }
QLabel#cardEmpty { color: $muted; font-size: 11px; font-style: italic; }
QLabel#iconPlaceholder {
    border-radius: 17px;
    background: $panel_2;
    color: $muted;
    font-size: 12px;
    font-weight: 700;
}

/* ---------- кнопки ---------- */
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
    color: $text;
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
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 $accent_hover, stop:1 $accent);
    border: 1px solid $accent;
    color: $on_accent;
    font-weight: 700;
}
QPushButton#primary:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 $accent, stop:1 $accent_hover);
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
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 $accent_hover, stop:1 $accent);
    border: 1px solid $accent;
    color: $on_accent;
    border-radius: 12px;
    font-size: 15px;
    font-weight: 700;
    padding: 12px 24px;
}
QPushButton#bigOverlay:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 $accent, stop:1 $accent_hover);
    border: 1px solid $accent_hover;
}
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
    background: $panel_2;
}

/* ---------- чипсы-фильтры (мета-тулбар) ---------- */
QPushButton#chip {
    background: $bg_alt;
    border: 1px solid transparent;
    border-radius: 12px;
    padding: 2px 12px;
    font-size: 12px;
    color: $muted;
}
QPushButton#chip:hover {
    border: 1px solid $accent;
    color: $text;
}
QPushButton#chip:checked {
    background: $accent;
    border: 1px solid $accent;
    color: $on_accent;
    font-weight: 600;
}

/* ---------- формы и ввод ---------- */
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

/* ---------- чекбоксы ---------- */
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

/* ---------- слайдеры ---------- */
QSlider::groove:horizontal {
    height: 6px;
    background: $input;
    border: 1px solid $border;
    border-radius: 3px;
}
QSlider::sub-page:horizontal {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 $accent_pressed, stop:1 $accent);
    border-radius: 3px;
}
QSlider::handle:horizontal {
    background: $accent_hover;
    width: 16px;
    height: 16px;
    margin: -6px 0;
    border-radius: 8px;
    border: 2px solid $bg;
}
QSlider::handle:horizontal:hover { background: $accent; }

/* ---------- таблица меты ---------- */
QTableWidget {
    background: transparent;
    alternate-background-color: $bg_alt;
    border: none;
    gridline-color: transparent;
    selection-background-color: $accent;
    selection-color: $on_accent;
}
QTableCornerButton::section { background: $panel; border: none; }
QHeaderView::section {
    background: $panel;
    color: $muted;
    border: none;
    border-bottom: 1px solid $border;
    padding: 5px 8px;
    font-size: 11px;
    font-weight: 700;
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

/* ---------- скроллбары ---------- */
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

/* ---------- статус, тултипы, меню ---------- */
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
    border-radius: 8px;
    padding: 6px 10px;
    font-size: 12px;
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
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 $accent_pressed, stop:1 $accent);
    border-radius: 6px;
}

/* ---------- оверлей (borderless, прозрачный, click-through) ---------- */
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
    """Собирает QSS из палитры (перевод строки замены не ломает)."""
    return _TEMPLATE.substitute(palette)


THEME_DARK: str = _render(_DARK)
THEME_LIGHT: str = _render(_LIGHT)


def theme_for(name: str) -> str:
    """'light' -> светлая тема, иначе тёмная (безопасный дефолт)."""
    return THEME_LIGHT if name == "light" else THEME_DARK
