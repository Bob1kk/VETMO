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
    "bg": "#0F1218",
    "bg_alt": "#141821",
    "panel": "#171C26",
    "panel_2": "#1E2431",
    "panel_3": "#252D3C",
    "text": "#EDF1F8",
    "muted": "#8E99AD",
    "border": "#2B3344",
    "accent": "#5B8DEF",
    "accent_hover": "#6E9CF2",
    "accent_pressed": "#4A78D8",
    "accent_soft": "#223354",
    "on_accent": "#FFFFFF",
    "danger": "#E35D6A",
    "ok": "#43C59E",
    "warning": "#E8B05A",
    "input": "#11151D",
    "scroll": "#394255",
    "overlay_panel": "rgba(15, 18, 24, 235)",
    "overlay_title": "#D7DDEA",
    "shadow": "rgba(0, 0, 0, 120)",
}

_LIGHT: dict[str, str] = {
    "bg": "#EEF1F6",
    "bg_alt": "#E7EBF2",
    "panel": "#FFFFFF",
    "panel_2": "#F3F5F9",
    "panel_3": "#E9EDF4",
    "text": "#172033",
    "muted": "#667287",
    "border": "#D6DCE6",
    "accent": "#3E6FE0",
    "accent_hover": "#5B8DEF",
    "accent_pressed": "#315BC0",
    "accent_soft": "#E4EBFC",
    "on_accent": "#FFFFFF",
    "danger": "#C93F4D",
    "ok": "#21896B",
    "warning": "#B87918",
    "input": "#FFFFFF",
    "scroll": "#C3C8D4",
    "overlay_panel": "rgba(255, 255, 255, 244)",
    "overlay_title": "#3A4150",
    "shadow": "rgba(0, 0, 0, 40)",
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
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 $panel, stop:0.55 $panel_2, stop:1 $panel);
    border: 1px solid $border;
    border-radius: 16px;
}
QLabel#brandMark {
    background: transparent;
    border: none;
    border-radius: 11px;
    color: $on_accent;
    font-size: 18px;
    font-weight: 800;
}
QLabel#brandTitle {
    color: $text;
    font-size: 21px;
    font-weight: 800;
    letter-spacing: 1px;
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
    border-radius: 10px;
    color: $muted;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.5px;
    padding: 3px 9px;
}
QTabWidget#sidebarTabs::pane {
    background: $panel;
    border: 1px solid $border;
    border-radius: 12px;
    top: -1px;
}
QTabBar::tab {
    background: transparent;
    border: none;
    border-bottom: 2px solid transparent;
    color: $muted;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.4px;
    padding: 7px 14px;
    margin-right: 2px;
}
QTabBar::tab:hover { color: $text; }
QTabBar::tab:selected {
    color: $text;
    border-bottom: 2px solid $accent;
}
QTabWidget#sidebarTabs QFrame#panel {
    background: transparent;
    border: none;
    border-radius: 0;
}

/* ---------- слои заголовков/бейджи ---------- */
QLabel#h1 { font-size: 19px; font-weight: 700; }
QLabel#h2 { font-size: 14px; font-weight: 600; }
QLabel#metaTitle { font-size: 18px; font-weight: 800; background: transparent; }
QLabel#metaSubtitle { color: $muted; font-size: 11px; background: transparent; }
QLabel#patchPill {
    background: $accent_soft;
    border: 1px solid $accent_pressed;
    border-radius: 999px;
    color: $accent_hover;
    font-size: 10px;
    font-weight: 800;
    letter-spacing: 0.5px;
    padding: 4px 10px;
}
QFrame#statCard {
    background: $panel_2;
    border: 1px solid $border;
    border-radius: 14px;
}
QLabel#statValue {
    color: $text;
    font-size: 17px;
    font-weight: 800;
    background: transparent;
}
QLabel#statLabel {
    color: $muted;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.5px;
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
    border-radius: 10px;
    color: $text;
    font-size: 10px;
    font-weight: 700;
}
QLabel#heroAttr { color: $muted; font-size: 10px; background: transparent; }
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
QLabel#delta, QLabel#deltaPos, QLabel#deltaNeg {
    font-size: 12px;
    font-weight: 700;
    background: transparent;
}
QLabel#deltaPos { color: $ok; }
QLabel#deltaNeg { color: $danger; }
QLabel#nodata { color: $muted; font-size: 12px; background: transparent; }
QLabel#metaHeroName {
    font-size: 13px;
    font-weight: 700;
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

/* ---------- панели и карточки ---------- */
QFrame#panel, QFrame#metaPanel {
    background: $panel;
    border: 1px solid $border;
    border-radius: 16px;
}
QFrame#metaToolbar {
    background: $panel_2;
    border: 1px solid $border;
    border-radius: 14px;
}
QFrame#newsList, QFrame#newsScroll { background: transparent; border: none; }
QFrame#newsRow {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 10px;
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
QLabel#cardName { color: $text; font-size: 12px; font-weight: 600; }
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
    border-radius: 10px;
    font-size: 13px;
    font-weight: 700;
    padding: 9px 18px;
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
QPushButton#headerGhost {
    background: transparent;
    border: 1px solid $border;
    color: $muted;
    border-radius: 9px;
    padding: 7px 12px;
    font-size: 12px;
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
    padding: 7px 8px;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.3px;
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
    border-radius: 16px;
}
QFrame#overlayHeader {
    background: transparent;
    border: none;
    border-bottom: 1px solid $border;
}
QLabel#overlayBrand {
    color: $overlay_title;
    font-size: 13px;
    font-weight: 800;
    letter-spacing: 1px;
}
QLabel#overlayStep {
    color: $accent_hover;
    font-size: 11px;
    font-weight: 700;
}
QLabel#overlaySource {
    color: $muted;
    font-size: 9px;
    letter-spacing: 0.4px;
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
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 $accent, stop:1 $accent_hover);
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
    font-weight: 800;
    letter-spacing: 1px;
    background: transparent;
}
QLabel#overlayTeamTitle[team="radiant"] { color: $ok; }
QLabel#overlayTeamTitle[team="dire"] { color: $danger; }
QLabel#overlayTeamCount {
    color: $muted;
    font-size: 9px;
    font-weight: 700;
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
    border-radius: 8px;
    color: $muted;
    font-size: 9px;
    font-weight: 800;
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
    border-radius: 9px;
    color: $muted;
    font-size: 13px;
    font-weight: 800;
    padding: 0;
}
QPushButton#overlaySlotClear:hover {
    background: $danger;
    color: $on_accent;
}
QLabel#overlaySuggestTitle {
    color: $muted;
    font-size: 9px;
    font-weight: 800;
    letter-spacing: 1px;
    background: transparent;
    padding-top: 2px;
}
QLabel#overlaySuggestPos {
    color: $accent_hover;
    font-size: 9px;
    font-weight: 700;
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
