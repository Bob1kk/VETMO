"""QSS-темы VETMO: тёмная и светлая.

Направление — «draft room»: тёплый графит с зеленоватым подтоном,
один янтарный акцент, спокойные поверхности и техничная типографика.
Без градиентов, свечений, эмодзи и uppercase-лейблов.
"""

from string import Template

__all__ = ["THEME_DARK", "THEME_LIGHT", "theme_for"]


_DARK: dict[str, str] = {
    "bg": "#0E120F",
    "bg_alt": "#131914",
    "panel": "#161D18",
    "panel_2": "#1C241E",
    "panel_3": "#253027",
    "text": "#F0F1E8",
    "muted": "#9AA69A",
    "border": "#2C372E",
    "accent": "#E7B24A",
    "accent_hover": "#F1C465",
    "accent_pressed": "#C69332",
    "accent_soft": "#332A18",
    "on_accent": "#1A1305",
    "danger": "#E26D6D",
    "ok": "#63C99A",
    "warning": "#E7B24A",
    "input": "#0B0F0C",
    "scroll": "#3D4A3F",
    "overlay_panel": "rgba(14, 18, 15, 238)",
    "overlay_title": "#E8EADF",
    "shadow": "rgba(0, 0, 0, 90)",
}

_LIGHT: dict[str, str] = {
    "bg": "#F4F1E8",
    "bg_alt": "#ECE8DC",
    "panel": "#FFFDF6",
    "panel_2": "#F5F1E7",
    "panel_3": "#EAE5D8",
    "text": "#1F261F",
    "muted": "#697367",
    "border": "#DCD5C6",
    "accent": "#B4741C",
    "accent_hover": "#C98A2D",
    "accent_pressed": "#8F5A12",
    "accent_soft": "#F6E7C8",
    "on_accent": "#FFFFFF",
    "danger": "#C24F52",
    "ok": "#2F8A63",
    "warning": "#A86A12",
    "input": "#FFFFFF",
    "scroll": "#C8C1B4",
    "overlay_panel": "rgba(255, 253, 246, 246)",
    "overlay_title": "#384035",
    "shadow": "rgba(29, 36, 29, 30)",
}

_TEMPLATE = Template(
    """
/* ---------- база ---------- */
QWidget {
    background: transparent;
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

/* ---------- каркас лаунчера ---------- */
QFrame#appHeader {
    background: $panel;
    border: 1px solid $border;
    border-bottom: 2px solid $accent;
    border-radius: 12px;
}
QLabel#brandMark {
    background: transparent;
    border: none;
    border-radius: 9px;
    color: $on_accent;
    font-size: 17px;
    font-weight: 600;
}
QLabel#brandTitle {
    color: $text;
    font-family: 'Bahnschrift', 'Segoe UI';
    font-size: 20px;
    font-weight: 600;
    background: transparent;
}
QLabel#brandSubtitle {
    color: $muted;
    font-size: 11px;
    background: transparent;
}
QLabel#headerPill {
    background: $panel_3;
    border: 1px solid $border;
    border-radius: 6px;
    color: $muted;
    font-size: 10px;
    font-weight: 500;
    padding: 4px 8px;
}
QTabWidget#sidebarTabs::pane {
    background: $panel;
    border: 1px solid $border;
    border-radius: 10px;
    top: -1px;
}
QTabBar::tab {
    background: transparent;
    border: none;
    border-bottom: 2px solid transparent;
    color: $muted;
    font-size: 12px;
    font-weight: 500;
    padding: 8px 12px;
    margin-right: 2px;
}
QTabBar::tab:hover { color: $text; }

QTabWidget#sidebarTabs::tab-bar {
    alignment: center;
}

QTabBar::tab:selected {
    color: $text;
    border-bottom: 2px solid $accent;
    /* Скругления убраны */
}
QTabWidget#sidebarTabs QFrame#panel {
    background: transparent;
    border: none;
    border-radius: 0;
}

/* ---------- слои заголовков/бейджи ---------- */
QLabel#h1 {
    font-family: 'Bahnschrift', 'Segoe UI';
    font-size: 19px;
    font-weight: 600;
}
QLabel#h2 { font-size: 14px; font-weight: 600; }
QLabel#metaTitle {
    font-family: 'Bahnschrift', 'Segoe UI';
    font-size: 19px;
    font-weight: 600;
    background: transparent;
}
QLabel#metaSubtitle { color: $muted; font-size: 11px; background: transparent; }
QLabel#patchPill {
    background: $accent_soft;
    border: 1px solid $accent_pressed;
    border-radius: 6px;
    color: $accent_hover;
    font-size: 10px;
    font-weight: 600;
    padding: 4px 8px;
}
QFrame#statCard {
    background: $panel_2;
    border: 1px solid $border;
    border-radius: 9px;
}
QLabel#statValue {
    color: $text;
    font-family: 'Cascadia Mono', 'Consolas';
    font-size: 18px;
    font-weight: 600;
    background: transparent;
}
QLabel#statLabel {
    color: $muted;
    font-size: 10px;
    font-weight: 500;
    background: transparent;
}
QLabel#countLabel { color: $muted; font-size: 11px; background: transparent; }
QLabel#stateInfo, QLabel#stateError {
    border-radius: 9px;
    font-size: 12px;
    padding: 8px 10px;
    background: $panel_2;
    border: 1px solid $border;
    color: $muted;
}
QLabel#stateError {
    color: $danger;
    border: 1px solid $danger;
}
QLabel#posBadge {
    background: $panel_3;
    border: 1px solid $border;
    border-radius: 6px;
    color: $text;
    font-size: 10px;
    font-weight: 600;
}
QLabel#heroAttr { color: $muted; font-size: 10px; background: transparent; }
QLabel#sectionTitle {
    font-size: 12px;
    font-weight: 600;
    color: $muted;
    background: transparent;
    padding: 2px 2px;
}
QLabel#sectionLabel {
    font-size: 11px;
    font-weight: 600;
    color: $muted;
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
QLabel#delta, QLabel#deltaPos, QLabel#deltaNeg {
    font-family: 'Cascadia Mono', 'Consolas';
    font-size: 12px;
    font-weight: 600;
    background: transparent;
}
QLabel#deltaPos { color: $ok; }
QLabel#deltaNeg { color: $danger; }
QLabel#nodata { color: $muted; font-size: 12px; background: transparent; }
QLabel#metaHeroName {
    font-size: 13px;
    font-weight: 600;
    background: transparent;
}
QLabel#metaRate {
    font-family: 'Cascadia Mono', 'Consolas';
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

/* ---------- панели и карточки ---------- */
QFrame#panel, QFrame#metaPanel {
    background: $panel;
    border: 1px solid $border;
    border-radius: 10px;
}
QFrame#metaToolbar {
    background: $panel_2;
    border: 1px solid $border;
    border-radius: 8px;
}
QFrame#newsList, QFrame#newsScroll { background: transparent; border: none; }
QFrame#newsRow {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 7px;
}
QFrame#newsRow:hover {
    background: $panel_2;
    border: 1px solid $border;
}
QFrame#heroCard {
    background: $panel;
    border: 1px solid $border;
    border-radius: 9px;
}
QFrame#heroCard:hover {
    border: 1px solid $accent;
}
QLabel#cardName { color: $text; font-size: 12px; font-weight: 600; }
QLabel#cardReason { color: $accent; font-size: 11px; background: transparent; }
QLabel#cardWr { color: $ok; font-size: 11px; font-weight: 600; }
QLabel#cardEmpty { color: $muted; font-size: 11px; font-style: italic; }
QLabel#iconPlaceholder {
    border-radius: 12px;
    background: $panel_2;
    color: $muted;
    font-size: 12px;
    font-weight: 600;
}

/* ---------- кнопки ---------- */
QPushButton {
    background: $panel_2;
    border: 1px solid $border;
    border-radius: 7px;
    padding: 7px 13px;
    color: $text;
    font-weight: 500;
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
    background: $accent;
    border: 1px solid $accent;
    color: $on_accent;
    font-weight: 600;
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
    color: rgba(255, 255, 255, 120);
}
QPushButton#bigOverlay {
    background: $accent;
    border: 1px solid $accent;
    color: $on_accent;
    border-radius: 8px;
    font-size: 13px;
    font-weight: 600;
    padding: 9px 16px;
}
QPushButton#bigOverlay:hover {
    background: $accent_hover;
    border: 1px solid $accent_hover;
}
QPushButton#bigOverlay:pressed { background: $accent_pressed; }
QPushButton#bigOverlay:disabled {
    background: $accent_pressed;
    color: rgba(255, 255, 255, 120);
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
QPushButton#headerGhost {
    background: transparent;
    border: 1px solid $border;
    color: $muted;
    border-radius: 7px;
    padding: 8px 11px;
    font-size: 12px;
    font-weight: 500;
}
QPushButton#headerGhost:hover {
    background: $panel_3;
    border: 1px solid $accent;
    color: $text;
}

/* ---------- чипсы-фильтры (мета-тулбар) ---------- */
QPushButton#chip {
    background: $bg_alt;
    border: 1px solid transparent;
    border-radius: 7px;
    padding: 4px 11px;
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
    border-radius: 6px;
    padding: 5px 8px;
    selection-background-color: $accent;
    selection-color: $on_accent;
}
QLineEdit#search {
    min-height: 22px;
    padding: 6px 11px;
    font-size: 12px;
}
QComboBox#filterCombo {
    min-height: 22px;
    padding: 5px 9px;
    font-size: 12px;
}
QPushButton#tiny {
    padding: 5px 10px;
    font-size: 11px;
    color: $muted;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
    border: 1px solid $accent;
}
QComboBox QAbstractItemView {
    background: $panel_2;
    border: 1px solid $border;
    selection-background-color: $accent;
    selection-color: $on_accent;
    outline: none;
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
    background: $accent;
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
QTableWidget#metaTable {
    background: transparent;
    alternate-background-color: $bg_alt;
    border: none;
}
QTableWidget#metaTable::item {
    border-bottom: 1px solid $border;
    padding: 0;
}
QTableCornerButton::section { background: $panel; border: none; }
QHeaderView {
    background: transparent;
    border: none;
}
QHeaderView::section {
    background: $panel;
    color: $muted;
    border: none;
    border-bottom: 1px solid $border;
    padding: 8px;
    font-size: 11px;
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
    background: $accent;
    border-radius: 6px;
}

/* ---------- оверлей (borderless, прозрачный, click-through) ---------- */
QWidget#overlayRoot { background: transparent; }
QFrame#overlayPanel {
    background: $overlay_panel;
    border: 1px solid $border;
    border-radius: 11px;
}
QFrame#overlayHeader {
    background: transparent;
    border: none;
    border-bottom: 1px solid $border;
}
QLabel#overlayBrand {
    color: $overlay_title;
    font-family: 'Bahnschrift', 'Segoe UI';
    font-size: 13px;
    font-weight: 600;
}
QLabel#overlayStep {
    color: $accent_hover;
    font-size: 11px;
    font-weight: 600;
}
QLabel#overlaySource {
    color: $muted;
    font-size: 9px;
}
QPushButton#overlayGear {
    background: $panel_2;
    border: 1px solid $border;
    border-radius: 13px;
    color: $text;
    font-size: 14px;
    padding: 0;
}
QPushButton#overlayGear:hover {
    background: $accent_soft;
    border: 1px solid $accent;
}
QPushButton#overlayGear:disabled {
    color: $muted;
    border: 1px solid $border;
    background: transparent;
}
QProgressBar#overlayProgress {
    background: $panel_3;
    border: none;
    border-radius: 2px;
    max-height: 4px;
    min-height: 4px;
}
QProgressBar#overlayProgress::chunk {
    background: $accent;
    border-radius: 2px;
}
QFrame#overlayTeamRadiant, QFrame#overlayTeamDire {
    background: $panel_2;
    border: 1px solid $border;
    border-radius: 11px;
}
QFrame#overlayTeamRadiant { border-left: 2px solid $ok; }
QFrame#overlayTeamDire { border-left: 2px solid $danger; }
QLabel#overlayTeamTitle {
    font-size: 10px;
    font-weight: 600;
    background: transparent;
}
QLabel#overlayTeamTitle[team="radiant"] { color: $ok; }
QLabel#overlayTeamTitle[team="dire"] { color: $danger; }
QLabel#overlayTeamCount {
    color: $muted;
    font-size: 9px;
    font-weight: 600;
    background: transparent;
}
QFrame#overlaySlot {
    background: $panel_3;
    border: 1px dashed $border;
    border-radius: 8px;
}
QFrame#overlaySlot:hover {
    background: $accent_soft;
    border: 1px dashed $accent;
}
QFrame#overlaySlot[filled="true"] {
    background: $panel_2;
    border: 1px solid $border;
}
QFrame#overlaySlot[filled="true"]:hover { border: 1px solid $accent; }
QLabel#overlaySlotBadge {
    background: $panel_3;
    border: 1px solid $border;
    border-radius: 6px;
    color: $muted;
    font-size: 9px;
    font-weight: 600;
}
QLabel#overlaySlotName {
    color: $text;
    font-size: 11px;
    font-weight: 600;
    background: transparent;
}
QPushButton#overlaySlotClear {
    background: transparent;
    border: none;
    border-radius: 6px;
    color: $muted;
    font-size: 13px;
    font-weight: 600;
    padding: 0;
}
QPushButton#overlaySlotClear:hover {
    background: $danger;
    color: $on_accent;
}
QLabel#overlaySuggestTitle {
    color: $muted;
    font-size: 9px;
    font-weight: 600;
    background: transparent;
    padding-top: 2px;
}
QLabel#overlaySuggestPos {
    color: $accent_hover;
    font-size: 9px;
    font-weight: 600;
    background: transparent;
}
QLabel#overlaySuggestHeroes {
    color: $text;
    font-size: 10px;
    font-weight: 600;
    background: transparent;
}
QLabel#overlayHint { color: $muted; font-size: 9px; background: transparent; }
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
