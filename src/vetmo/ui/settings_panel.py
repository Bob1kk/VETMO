"""Правая панель лаунчера: настройки оверлея + синхронизация (T-009/T-010).

Все записи настроек и сеть делает родитель (MainWindow) через колбэки —
коммит идёт в worker-потоке, панель только собирает значения.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractSpinBox,
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

from vetmo.ui.monitor import available_screens, screen_label


class SettingsPanel(QFrame):
    """Настройки оверлея: позиция, непрозрачность, тема, флаги."""

    settings_committed = Signal(str, object)  # (kind, value)
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
        self.setMinimumWidth(300)
        self._commit_callbacks: dict[str, object] = {}
        self._build_ui(app_version)
        self.load(initial)

    # --- построение ---
    def _build_ui(self, app_version: str) -> None:
        title = QLabel("Настройки", self)
        title.setObjectName("metaTitle")
        subtitle = QLabel("Оверлей и данные", self)
        subtitle.setObjectName("metaSubtitle")

        # Позиция оверлея
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(6)
        self._pos_x = QSpinBox(self)
        self._pos_x.setRange(0, 4096)
        self._pos_x.setSuffix(" px")
        self._pos_x.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self._pos_x.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._pos_y = QSpinBox(self)
        self._pos_y.setRange(0, 4096)
        self._pos_y.setSuffix(" px")
        self._pos_y.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self._pos_y.setAlignment(Qt.AlignmentFlag.AlignRight)
        form.addRow("Позиция X:", self._pos_x)
        form.addRow("Позиция Y:", self._pos_y)

        # Монитор: лаунчер и оверлей открываются на выбранном экране.
        self._monitor = QComboBox(self)
        self._monitor.setObjectName("filterCombo")
        self._fill_monitors()

        # Непрозрачность
        opacity_label = QLabel("Непрозрачность", self)
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
            "Мышь проходит сквозь оверлей. Шестерёнка в оверлее будет "
            "недоступна — настройки открываются из этого окна.")
        self._show_dire = QCheckBox("Показать пики Dire", self)

        # Кнопки оверлея/синхронизации
        self._overlay_button = self._button(
            "Показать оверлей", "secondary")
        self._overlay_button.clicked.connect(
            self.overlay_toggle_requested.emit)
        self._sync_button = self._button("Обновить данные", "secondary")
        self._sync_button.setToolTip(
            "Перечитать мету, патчи и новости из Supabase. "
            "Обновление reference-данных выполняет sync-скрипт по расписанию.")
        self._sync_button.clicked.connect(
            lambda: self.sync_requested.emit(0))  # 0 — все герои
        self._supabase_note = QLabel(self)
        self._supabase_note.setObjectName("mutedSmall")
        self._supabase_note.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 12)
        layout.setSpacing(9)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(2)
        layout.addWidget(self._section("ОВЕРЛЕЙ"))
        layout.addLayout(form)
        layout.addWidget(QLabel("Монитор:", self))
        layout.addWidget(self._monitor)
        layout.addLayout(opacity_row)
        layout.addWidget(self._opacity)
        layout.addWidget(QLabel("Тема:", self))
        layout.addWidget(self._theme)
        layout.addWidget(self._click_through)
        layout.addWidget(self._show_dire)
        layout.addWidget(self._overlay_button)
        layout.addSpacing(4)
        layout.addWidget(self._section("ДАННЫЕ"))
        layout.addWidget(self._sync_button)
        layout.addWidget(self._supabase_note)
        layout.addStretch(1)

        version = QLabel(f"Версия VETMO {app_version}", self)
        version.setObjectName("mutedSmall")
        layout.addWidget(version)

        self._connect_signals()

    @staticmethod
    def _section(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("sectionTitle")
        return label

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
        self._monitor.activated.connect(self._commit_monitor)
        self._click_through.toggled.connect(self._commit_click_through)
        self._show_dire.toggled.connect(self._commit_show_dire)

    def _fill_monitors(self) -> None:
        """Список экранов: -1 — «второй, если есть»."""
        self._monitor.clear()
        screens = available_screens()
        if len(screens) > 1:
            self._monitor.addItem("Второй монитор (если есть)", -1)
        for index, screen in enumerate(screens):
            suffix = " (основной)" if index == 0 else ""
            self._monitor.addItem(
                screen_label(index, screen) + suffix, index)
        if not screens:
            self._monitor.addItem("Основной монитор", 0)

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
        monitor_index = int(initial.get("monitor", -1))
        monitor_pos = self._monitor.findData(monitor_index)
        if monitor_pos < 0:
            monitor_pos = self._monitor.findData(-1)
        self._monitor.setCurrentIndex(max(0, monitor_pos))
        self._click_through.setChecked(
            bool(initial.get("click_through", False)))
        self._show_dire.setChecked(bool(initial.get("show_dire", True)))

    def set_sync_enabled(self, enabled: bool) -> None:
        """Вида кнопки синхронизации (busy-состояние в статусбаре)."""
        self._sync_button.setEnabled(enabled)

    def set_overlay_visible(self, visible: bool) -> None:
        """Синхронизирует текст кнопки с реальным состоянием оверлея."""
        self._overlay_button.setText(
            "Скрыть оверлей" if visible else "Показать оверлей")

    def set_supabase_note(self, enabled: bool) -> None:
        """Статус Supabase: подключён (STRATZ) либо не настроен."""
        self._supabase_note.setText(
            "Supabase: подключён · данные STRATZ"
            if enabled else
            "Supabase: не настроен · проверьте VETMO_SUPABASE_*")

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

    def _commit_monitor(self, index: int) -> None:
        self.settings_committed.emit(
            "monitor", int(self._monitor.itemData(index) or 0))

    def _commit_click_through(self, checked: bool) -> None:
        self.settings_committed.emit("click_through", checked)

    def _commit_show_dire(self, checked: bool) -> None:
        self.settings_committed.emit("show_dire", checked)
