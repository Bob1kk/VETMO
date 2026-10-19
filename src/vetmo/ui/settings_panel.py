"""Правая панель лаунчера: настройки оверлея + синхронизация (T-009/T-010).

Все записи настроек и сеть делает родитель (MainWindow) через колбэки —
коммит идёт в worker-потоке, панель только собирает значения.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

_ACCENT = "#5B8DEF"


class SettingsPanel(QFrame):
    """Настройки оверлея: позиция, прозрачность, тема, флаги, приоритеты."""

    settings_committed = Signal(str, object)  # (kind, value)
    priorities_requested = Signal()
    sync_requested = Signal(int)              # limit героев
    manual_pick_requested = Signal()
    overlay_toggle_requested = Signal()

    _THEME_LABELS = (("Тёмная", "dark"), ("Светлая", "light"))

    def __init__(
        self,
        initial: dict,  # {position:(x,y), opacity:float, theme:str,
        #                 click_through:bool, show_dire:bool}
        app_version: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("panel")
        self.setMinimumWidth(280)
        self._commit_callbacks: dict[str, object] = {}
        self._build_ui(app_version)
        self.load(initial)

    # --- построение ---
    def _build_ui(self, app_version: str) -> None:
        title = QLabel("⚙ НАСТРОЙКИ ОВЕРЛЕЯ", self)
        title.setObjectName("sectionTitle")

        # Позиция оверлея
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form.setContentsMargins(0, 0, 0, 0)
        self._pos_x = QSpinBox(self)
        self._pos_x.setRange(0, 4096)
        self._pos_y = QSpinBox(self)
        self._pos_y.setRange(0, 4096)
        form.addRow("X:", self._pos_x)
        form.addRow("Y:", self._pos_y)

        # Прозрачность
        opacity_label = QLabel("Прозрачность:", self)
        self._opacity_value = QLabel(self)
        self._opacity_value.setObjectName("muted")
        opacity_row = QHBoxLayout()
        opacity_row.setContentsMargins(0, 0, 0, 0)
        opacity_row.addWidget(opacity_label)
        opacity_row.addStretch(1)
        opacity_row.addWidget(self._opacity_value)
        self._opacity = QSlider(Qt.Orientation.Horizontal, self)
        self._opacity.setRange(10, 100)

        # Тема
        self._theme = QComboBox(self)
        for label, code in self._THEME_LABELS:
            self._theme.addItem(label, code)

        # Флаги
        self._click_through = QCheckBox(
            "Прозрачный для клика (click-through)", self)
        self._click_through.setToolTip(
            "Мышь проходит сквозь оверлей — подход работает только с "
            "клавиатурным управлением из лаунчера.")
        self._show_dire = QCheckBox("Показать пики Dire", self)

        # Приоритеты
        priorities_button = self._button(
            "Настроить приоритеты позиций…", "secondary")
        priorities_button.clicked.connect(self.priorities_requested.emit)

        # Синхронизация
        self._sync_button = self._button("Синхронизировать данные", "secondary")
        self._sync_button.setToolTip(
            "Загружает героев и матчапы из OpenDota (до ~15 секунд).")
        self._sync_button.clicked.connect(
            lambda: self.sync_requested.emit(120))
        self._supabase_note = QLabel(self)
        self._supabase_note.setObjectName("mutedSmall")
        self._supabase_note.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        layout.addWidget(title)
        layout.addLayout(form)
        layout.addLayout(opacity_row)
        layout.addWidget(self._opacity)
        layout.addWidget(QLabel("Тема:", self))
        layout.addWidget(self._theme)
        layout.addWidget(self._click_through)
        layout.addWidget(self._show_dire)
        layout.addWidget(priorities_button)
        layout.addWidget(self._sync_button)
        layout.addWidget(self._supabase_note)
        layout.addStretch(1)

        version = QLabel(f"Версия VETMO {app_version}", self)
        version.setObjectName("mutedSmall")
        layout.addWidget(version)

        self._connect_signals()

    @staticmethod
    def _button(text: str, kind: str = "secondary") -> QPushButton:
        button = QPushButton(text)
        button.setObjectName(kind)
        return button

    def _connect_signals(self) -> None:
        self._opacity.sliderReleased.connect(self._commit_opacity)
        self._opacity.valueChanged.connect(self._update_opacity_label)
        self._pos_x.editingFinished.connect(self._commit_position)
        self._pos_y.editingFinished.connect(self._commit_position)
        self._theme.activated.connect(self._commit_theme)
        self._click_through.toggled.connect(self._commit_click_through)
        self._show_dire.toggled.connect(self._commit_show_dire)

    # --- загрузка/выгрузка значений ---
    def load(self, initial: dict) -> None:
        """Применяет значения, не отправляя коммиты."""
        x, y = initial.get("position", (20, 20))
        opacity = int(round(float(initial.get("opacity", 0.85)) * 100))
        self._pos_x.setValue(int(x))
        self._pos_y.setValue(int(y))
        self._opacity.setValue(max(10, min(100, opacity)))
        theme = str(initial.get("theme", "dark"))
        index = self._theme.findData(theme)
        self._theme.setCurrentIndex(index if index >= 0 else 0)
        self._click_through.setChecked(bool(initial.get("click_through", True)))
        self._show_dire.setChecked(bool(initial.get("show_dire", True)))

    def set_sync_enabled(self, enabled: bool) -> None:
        """Вида кнопки синхронизации (busy-состояние в статусбаре)."""
        self._sync_button.setEnabled(enabled)

    def set_supabase_note(self, enabled: bool) -> None:
        """Пояснение про Supabase (env-переменные)."""
        self._supabase_note.setText(
            "Supabase: подключён (облачная синхронизация)."
            if enabled else
            "Supabase: не настроен (локальная БД, офлайн-режим).")

    # --- коммиты (родитель делает запись в БД из worker) ---
    def _commit_position(self) -> None:
        self.settings_committed.emit(
            "position", (self._pos_x.value(), self._pos_y.value()))

    def _commit_opacity(self) -> None:
        self.settings_committed.emit(
            "opacity", self._opacity.value() / 100.0)

    def _update_opacity_label(self) -> None:
        self._opacity_value.setText(f"{self._opacity.value()}%")

    def _commit_theme(self, index: int) -> None:
        self.settings_committed.emit("theme", self._theme.itemData(index))

    def _commit_click_through(self, checked: bool) -> None:
        self.settings_committed.emit("click_through", checked)

    def _commit_show_dire(self, checked: bool) -> None:
        self.settings_committed.emit("show_dire", checked)
