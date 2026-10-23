"""Окно оверлея: borderless, always-on-top, прозрачный фон, click-through (T-011).

Не крадёт фокус у Dota 2 (Review Focus #2): Qt.Tool +
WA_ShowWithoutActivating + NoFocus; при click-through мышь проходит
насквозь. Позиция/непрозрачность/флаги читаются из SettingsService.

Доска драфта: у каждой команды 5 кликабельных клеток (позиции 1..5).
Клик открывает выбор героя с фильтром по атрибутам; выбранные герои
учитываются в блоке подсказок «снизу». Шапка окна — зона перетаскивания.

Кнопка-шестерёнка открывает настройки в лаунчере через ``settings_requested``.
При включённом click-through она недоступна (мышь физически проходит сквозь
окно) — рядом показывается явная подсказка, а не «мёртвая» кнопка.
"""

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from vetmo.domain.models import Hero
from vetmo.services.settings_service import SettingsService
from vetmo.ui.monitor import overlay_top_left, resolve_screen
from vetmo.ui.viewmodels.overlay_vm import OverlayEntry, OverlaySnapshot
from vetmo.ui.widgets.hero_pick_dialog import HeroPickDialog
from vetmo.ui.widgets.pick_slot import PickSlot
from vetmo.ui.workers import start_worker

# Сколько имён героев показывать в строке одной позиции (остальные — «+N»).
_SUGGESTION_HEROES = 4


class DragHeader(QFrame):
    """Шапка оверлея: тянет окно мышью и сообщает новую позицию."""

    moved = Signal(int, int)  # координаты относительно текущего экрана

    def __init__(self, window: QWidget, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._window = window
        self._offset: QPoint | None = None
        self.setObjectName("overlayHeader")
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        self.setToolTip("Перетащите за шапку, чтобы переместить оверлей")

    def mousePressEvent(self, event) -> None:  # noqa: N802 — Qt API
        if event.button() == Qt.MouseButton.LeftButton:
            self._offset = (
                event.globalPosition().toPoint()
                - self._window.frameGeometry().topLeft()
            )
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 — Qt API
        if self._offset is not None and (
            event.buttons() & Qt.MouseButton.LeftButton
        ):
            self._window.move(event.globalPosition().toPoint() - self._offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 — Qt API
        if self._offset is not None and event.button() == Qt.MouseButton.LeftButton:
            self._offset = None
            self._emit_position()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _emit_position(self) -> None:
        screen = self._window.screen() or resolve_screen(-1)
        area = screen.availableGeometry() if screen is not None else None
        x = self._window.x() - (area.x() if area is not None else 0)
        y = self._window.y() - (area.y() if area is not None else 0)
        self.moved.emit(max(0, x), max(0, y))


class SuggestionRow(QWidget):
    """Строка подсказок незанятой позиции: «Поз. 5 · A · B · C».

    Полный список с винрейтом и причиной — в тултипе: в оверлее важно
    показать больше героев на каждую позицию, не раздувая высоту окна.
    """

    def __init__(
        self,
        position: int,
        entries: list[OverlayEntry],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)

        badge = QLabel(f"Поз. {position}", self)
        badge.setObjectName("overlaySuggestPos")
        badge.setFixedWidth(38)

        names = " · ".join(
            entry.hero.localized_name for entry in entries[:_SUGGESTION_HEROES]
        )
        if len(entries) > _SUGGESTION_HEROES:
            names += f" · +{len(entries) - _SUGGESTION_HEROES}"
        text = QLabel(names or "—", self)
        text.setObjectName("overlaySuggestHeroes")
        text.setWordWrap(False)
        self._names = text

        row.addWidget(badge, 0)
        row.addWidget(text, 1)

        tooltip = self._tooltip(entries)
        self.setToolTip(tooltip)
        badge.setToolTip(tooltip)
        text.setToolTip(tooltip)

    @staticmethod
    def _tooltip(entries: list[OverlayEntry]) -> str:
        lines: list[str] = []
        for entry in entries:
            parts = [entry.hero.localized_name]
            wr = entry.wr_text()
            if wr:
                parts.append(wr)
            parts.append(entry.reason)
            lines.append(" · ".join(parts))
        return "\n".join(lines)


class OverlayColumn(QFrame):
    """Колонка команды: 5 клеток пиков + подсказки по незанятым позициям."""

    pick_clicked = Signal(str, int)
    clear_clicked = Signal(str, int)

    def __init__(self, team: str, title: str,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName(
            "overlayTeamRadiant" if team == "radiant" else "overlayTeamDire")
        self.setMinimumWidth(300)
        self._team = team
        self._slots: dict[int, PickSlot] = {}

        header = QLabel(title.upper(), self)
        header.setObjectName("overlayTeamTitle")
        header.setProperty("team", team)
        self._count = QLabel("0/5", self)
        self._count.setObjectName("overlayTeamCount")
        self._count.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(6)
        title_row.addWidget(header)
        title_row.addStretch(1)
        title_row.addWidget(self._count)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 9)
        layout.setSpacing(4)
        layout.addLayout(title_row)

        for position in range(1, 6):
            slot = PickSlot(team, position, self)
            slot.clicked.connect(
                lambda pos=position: self.pick_clicked.emit(self._team, pos))
            slot.clear_clicked.connect(
                lambda pos=position: self.clear_clicked.emit(self._team, pos))
            layout.addWidget(slot)
            self._slots[position] = slot

        suggest_caption = QLabel("ПОДСКАЗКИ", self)
        suggest_caption.setObjectName("overlaySuggestTitle")
        layout.addWidget(suggest_caption)

        self._suggestions = QVBoxLayout()
        self._suggestions.setContentsMargins(0, 0, 0, 0)
        self._suggestions.setSpacing(2)
        layout.addLayout(self._suggestions)

    # --- данные ---
    def fill(self, snapshot: OverlaySnapshot) -> None:
        """Заполняет клетки пиками, а строки — подсказками по позициям."""
        picked = snapshot.picked.get(self._team, {})
        for position, slot in self._slots.items():
            hero = picked.get(position)
            if hero is None:
                slot.set_empty()
                continue
            slot.set_hero(hero)
        self._refresh_count()

        self._clear_suggestions()
        columns = snapshot.columns.get(self._team, {})
        for position in sorted(columns):
            self._suggestions.addWidget(
                SuggestionRow(position, columns[position], self))
        if not columns:
            done = QLabel("Все позиции выбраны", self)
            done.setObjectName("overlaySuggestHeroes")
            self._suggestions.addWidget(done)

    def _clear_suggestions(self) -> None:
        """Удаляет строки предыдущего снимка (иначе они копятся)."""
        while self._suggestions.count():
            item = self._suggestions.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.deleteLater()

    def set_slot_hero(self, position: int, hero: Hero | None) -> None:
        """Немедленно ставит/убирает героя в клетке (до пересчёта снимка)."""
        slot = self._slots.get(position)
        if slot is None:
            return
        if hero is None:
            slot.set_empty()
        else:
            slot.set_hero(hero)
        self._refresh_count()

    def _refresh_count(self) -> None:
        """Счётчик «N/5» по фактически заполненным клеткам."""
        filled = sum(
            1 for slot in self._slots.values() if slot.hero() is not None)
        self._count.setText(f"{filled}/5")

    def set_team_visible(self, visible: bool) -> None:
        """Прячет/показывает колонку (Dire настраивается в лаунчере)."""
        self.setVisible(visible)


class OverlayWindow(QWidget):
    """Окно оверлея, привязываемое в OverlayService через getattr-API."""

    refresh_requested = Signal()
    settings_requested = Signal()
    pick_requested = Signal(str, int, int)  # team, position, hero_id
    clear_requested = Signal(str, int)      # team, position
    position_changed = Signal(int, int)     # x, y относительно экрана

    def __init__(self, settings_service: SettingsService,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("VETMO Overlay")
        self._settings = settings_service
        self._heroes_loader = None
        self._matchup_loader = None
        self._current_picked: dict[str, dict[int, Hero | None]] = {
            "radiant": {}, "dire": {},
        }

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        panel = QFrame(self)
        panel.setObjectName("overlayPanel")
        header = DragHeader(self, self)
        header_row = QHBoxLayout(header)
        header_row.setContentsMargins(2, 1, 2, 1)
        header_row.setSpacing(8)
        brand = QLabel("VETMO", self)
        brand.setObjectName("overlayBrand")
        self._step = QLabel("00/10 · RADIANT", self)
        self._step.setObjectName("overlayStep")
        self._step.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._lock_hint = QLabel("CLICK-THROUGH", self)
        self._lock_hint.setObjectName("overlayHint")
        self._lock_hint.setToolTip(
            "Мышь проходит сквозь оверлей. Отключите click-through в "
            "настройках лаунчера, чтобы пользоваться клетками и шестерёнкой.")
        self._gear = QPushButton("⚙", self)
        self._gear.setObjectName("overlayGear")
        self._gear.setFixedSize(24, 24)
        self._gear.setCursor(Qt.CursorShape.PointingHandCursor)
        self._gear.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._gear.setToolTip("Настройки оверлея")
        self._gear.clicked.connect(self.settings_requested.emit)
        header_row.addWidget(brand)
        header_row.addStretch(1)
        header_row.addWidget(self._step)
        header_row.addWidget(self._lock_hint)
        header_row.addWidget(self._gear)
        header.moved.connect(self.position_changed.emit)
        self._header = header

        self._progress = QProgressBar(self)
        self._progress.setObjectName("overlayProgress")
        self._progress.setRange(0, 10)
        self._progress.setValue(0)
        self._progress.setTextVisible(False)
        self._progress.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._radiant = OverlayColumn("radiant", "Radiant", self)
        self._dire = OverlayColumn("dire", "Dire", self)
        for column in (self._radiant, self._dire):
            column.pick_clicked.connect(self._open_pick_dialog)
            column.clear_clicked.connect(self.clear_requested.emit)
        columns = QHBoxLayout()
        columns.setContentsMargins(0, 0, 0, 0)
        columns.setSpacing(8)
        columns.addWidget(self._radiant)
        columns.addWidget(self._dire)

        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(12, 10, 12, 11)
        panel_layout.setSpacing(7)
        panel_layout.addWidget(header)
        panel_layout.addWidget(self._progress)
        panel_layout.addLayout(columns)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(panel)
        self._update_gear_state()

    def set_matchup_loader(self, loader) -> None:
        """Совместимость с MainWindow: подсказки-строки без rich-тултипов."""
        self._matchup_loader = loader

    def set_heroes_loader(self, loader) -> None:
        """loader() -> list[Hero]: каталог для диалога выбора героя."""
        self._heroes_loader = loader

    # --- контракт OverlayService (вызывается через getattr) ---
    def show_overlay(self) -> None:
        """Показывает оверлей: позиция/непрозрачность/флаги из настроек."""
        self._apply_settings()
        self.show()
        self.adjustSize()

    def hide_overlay(self) -> None:
        """Скрывает оверлей (лаунчер остаётся видимым)."""
        self.hide()

    def update_overlay(self) -> None:
        """Пинг обновления рекомендаций/шага (работу делает MainWindow)."""
        self.refresh_requested.emit()

    # --- данные ---
    def apply_pick(self, team: str, position: int, hero: Hero) -> None:
        """Оптимистично ставит героя в клетку — не ждём пересчёта снимка.

        Пересчёт рекомендаций может идти секунды; без этого клетка «не
        реагировала» на выбор героя.
        """
        column = self._column_for(team)
        if column is None:
            return
        column.set_slot_hero(position, hero)
        self._current_picked.setdefault(team, {})[position] = hero

    def apply_clear(self, team: str, position: int) -> None:
        """Оптимистично очищает клетку до прихода нового снимка."""
        column = self._column_for(team)
        if column is None:
            return
        column.set_slot_hero(position, None)
        self._current_picked.setdefault(team, {}).pop(position, None)

    def _column_for(self, team: str) -> OverlayColumn | None:
        if team == "radiant":
            return self._radiant
        if team == "dire":
            return self._dire
        return None

    def apply_snapshot(self, snapshot: OverlaySnapshot) -> None:
        """Применяет снимок OverlayViewModel: клетки, подсказки, шаг и прогресс."""
        show_dire = self._settings.get_show_dire()
        self._dire.set_team_visible(show_dire)
        self._current_picked = snapshot.picked
        self._radiant.fill(snapshot)
        if show_dire:
            self._dire.fill(snapshot)
        team = snapshot.next_team.upper()
        self._step.setText(
            f"{snapshot.step:02d}/{snapshot.total:02d} · {team}")
        self._progress.setMaximum(max(1, snapshot.total))
        self._progress.setValue(min(snapshot.step, snapshot.total))
        if self.isVisible():
            self.adjustSize()

    # --- внутренние ---
    def apply_settings(self) -> None:
        """Публичное имя для лаунчера: позиция/непрозрачность/флаги."""
        self._apply_settings()

    def _apply_settings(self) -> None:
        """Позиция, непрозрачность, click-through — из SettingsService."""
        was_visible = self.isVisible()
        x, y = self._settings.get_overlay_position()
        get_monitor = getattr(self._settings, "get_monitor_index", None)
        monitor_index = int(get_monitor()) if callable(get_monitor) else -1
        self.move(overlay_top_left(resolve_screen(monitor_index), x, y))
        self.setWindowOpacity(max(0.1, min(1.0, self._settings.get_opacity())))
        click_through = self._settings.get_click_through()
        flag = Qt.WindowType.WindowTransparentForInput
        if bool(self.windowFlags() & flag) != click_through:
            # setWindowFlag на видимом окне пересоздаёт native window и
            # скрывает его — возвращаем оверлей на экран после смены флага.
            self.setWindowFlag(flag, click_through)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._update_gear_state()
        if was_visible and not self.isVisible():
            self.show()
            self.adjustSize()

    def _open_pick_dialog(self, team: str, position: int) -> None:
        """Загружает каталог в worker и открывает диалог выбора героя."""
        if self._heroes_loader is None:
            QMessageBox.information(
                self, "Каталог недоступен",
                "Список героев ещё не загружен. Откройте лаунчер и повторите.")
            return
        current = self._current_picked.get(team, {}).get(position)
        current_id = current.id if current is not None else None

        def done(heroes: object) -> None:
            if not isinstance(heroes, list) or not heroes:
                QMessageBox.information(
                    self, "Каталог пуст",
                    "Не удалось получить список героев. Обновите данные.")
                return
            # Уже пикнутых героев не предлагаем: иначе set_pick падает
            # с «герой уже пикнут» и пользователь видит ошибку вместо выбора.
            taken = {
                hero.id
                for picked in self._current_picked.values()
                for hero in picked.values()
                if hero is not None
            }
            if current_id is not None:
                taken.discard(current_id)
            available = [hero for hero in heroes if hero.id not in taken]
            if not available:
                QMessageBox.information(
                    self, "Все герои выбраны",
                    "Все герои каталога уже пикнуты. Очистите клетку, чтобы "
                    "выбрать другого.")
                return
            dialog = HeroPickDialog(
                available, team, position, current_id, None)
            dialog.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
            dialog.hero_selected.connect(
                lambda hero_id: self.pick_requested.emit(
                    team, position, hero_id))
            dialog.adjustSize()
            center = self.frameGeometry().center()
            dialog.move(center.x() - dialog.width() // 2,
                        center.y() - dialog.height() // 2)
            # Оверлей — always-on-top Tool: без явного поднятия диалог может
            # открыться позади и выглядеть как «зависшее» приложение.
            dialog.raise_()
            dialog.activateWindow()
            dialog.exec()

        def fail(message: str) -> None:
            QMessageBox.warning(
                self, "Не удалось загрузить героев", message)

        start_worker(self._heroes_loader, on_done=done, on_fail=fail)

    def _update_gear_state(self) -> None:
        """Шестерёнка активна только без click-through; иначе — подсказка."""
        locked = bool(self._settings.get_click_through())
        self._gear.setEnabled(not locked)
        self._lock_hint.setVisible(locked)
        self._gear.setToolTip(
            "Настройки: сначала отключите click-through в лаунчере"
            if locked else "Настройки оверлея"
        )
