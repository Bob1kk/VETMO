"""Окно оверлея: borderless, always-on-top, прозрачный фон, click-through (T-011).

Не крадёт фокус у Dota 2 (Review Focus #2): Qt.Tool +
WA_ShowWithoutActivating + NoFocus; при click-through мышь проходит
насквозь. Позиция/прозрачность/флаги читаются из SettingsService.

Кнопка-шестерёнка открывает настройки в лаунчере через ``settings_requested``.
При включённом click-through она недоступна (мышь физически проходит сквозь
окно) — рядом показывается явная подсказка, а не «мёртвая» кнопка.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from vetmo.services.settings_service import SettingsService
from vetmo.ui.viewmodels.overlay_vm import OverlaySnapshot
from vetmo.ui.widgets.hero_card import HeroCard

_CARDS_PER_POSITION = 2


class OverlayColumn(QFrame):
    """Колонка команды: заголовок + 5 позиций с карточками героев."""

    def __init__(self, team: str, title: str,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName(
            "overlayTeamRadiant" if team == "radiant" else "overlayTeamDire")
        self.setMinimumWidth(286)
        self._team = team
        self._cards: dict[int, list[HeroCard]] = {}

        header = QLabel(title.upper(), self)
        header.setObjectName("overlayTeamTitle")
        header.setProperty("team", team)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 9)
        layout.setSpacing(4)
        layout.addWidget(header)

        for position in range(1, 6):
            position_row = QHBoxLayout()
            position_row.setContentsMargins(0, 2, 0, 0)
            position_row.setSpacing(6)
            badge = QLabel(str(position), self)
            badge.setObjectName("overlayPosBadge")
            badge.setFixedSize(18, 18)
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            caption = QLabel(f"ПОЗИЦИЯ {position}", self)
            caption.setObjectName("overlayPosLabel")
            position_row.addWidget(badge)
            position_row.addWidget(caption)
            position_row.addStretch(1)
            layout.addLayout(position_row)
            cards = [HeroCard(self) for _ in range(_CARDS_PER_POSITION)]
            for card in cards:
                card.setObjectName("overlayCard")
                card.setSizePolicy(
                    QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
                card.setMaximumHeight(48)
                layout.addWidget(card)
            self._cards[position] = cards

    def fill(self, snapshot: OverlaySnapshot) -> None:
        """Заполняет карточки: пикнутый герой либо рекомендации позиции."""
        entries = snapshot.columns.get(self._team, {})
        picked = snapshot.picked.get(self._team, {})
        for position, cards in self._cards.items():
            picked_hero = picked.get(position)
            recs = entries.get(position, [])
            if picked_hero is not None:
                cards[0].show_hero(picked_hero, reason="Пик записан")
                cards[1].hide()
                continue
            cards[1].show()
            for index, card in enumerate(cards):
                if index < len(recs):
                    entry = recs[index]
                    card.show_hero(
                        entry.hero, reason=entry.reason,
                        wr_text=entry.wr_text(),
                    )
                else:
                    card.set_empty("рекомендаций нет — синхронизируйте данные")

    def set_team_visible(self, visible: bool) -> None:
        """Прячет/показывает колонку (Dire настраивается в лаунчере)."""
        self.setVisible(visible)

    def set_matchup_loader(self, loader) -> None:
        """Раздаёт loader(hero_id) всем карточкам колонки (тултипы R2)."""
        for cards in self._cards.values():
            for card in cards:
                card.set_matchup_loader(loader)


class OverlayWindow(QWidget):
    """Окно оверлея, привязываемое в OverlayService через getattr-API."""

    refresh_requested = Signal()
    settings_requested = Signal()

    def __init__(self, settings_service: SettingsService,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("VETMO Overlay")
        self._settings = settings_service

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
        header = QFrame(self)
        header.setObjectName("overlayHeader")
        header_row = QHBoxLayout(header)
        header_row.setContentsMargins(2, 1, 2, 1)
        header_row.setSpacing(8)
        brand = QLabel("VETMO", self)
        brand.setObjectName("overlayBrand")
        source = QLabel("OPENDOTA · LIVE", self)
        source.setObjectName("overlaySource")
        self._step = QLabel("00/10 · RADIANT", self)
        self._step.setObjectName("overlayStep")
        self._step.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._lock_hint = QLabel("CLICK-THROUGH", self)
        self._lock_hint.setObjectName("overlayHint")
        self._lock_hint.setToolTip(
            "Мышь проходит сквозь оверлей. Отключите click-through в "
            "настройках лаунчера, чтобы пользоваться шестерёнкой.")
        self._gear = QPushButton("⚙", self)
        self._gear.setObjectName("overlayGear")
        self._gear.setFixedSize(24, 24)
        self._gear.setCursor(Qt.CursorShape.PointingHandCursor)
        self._gear.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._gear.setToolTip("Настройки оверлея")
        self._gear.clicked.connect(self.settings_requested.emit)
        header_row.addWidget(brand)
        header_row.addWidget(source)
        header_row.addStretch(1)
        header_row.addWidget(self._step)
        header_row.addWidget(self._lock_hint)
        header_row.addWidget(self._gear)

        self._progress = QProgressBar(self)
        self._progress.setObjectName("overlayProgress")
        self._progress.setRange(0, 10)
        self._progress.setValue(0)
        self._progress.setTextVisible(False)
        self._progress.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._radiant = OverlayColumn("radiant", "Radiant", self)
        self._dire = OverlayColumn("dire", "Dire", self)
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
        """loader(hero_id) -> (strong, weak) | None — ленивые тултипы (B)."""
        for column in (self._radiant, self._dire):
            column.set_matchup_loader(loader)

    # --- контракт OverlayService (вызывается через getattr) ---
    def show_overlay(self) -> None:
        """Показывает оверлей: позиция/прозрачность/флаги из настроек."""
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
    def apply_snapshot(self, snapshot: OverlaySnapshot) -> None:
        """Применяет снимок OverlayViewModel: колонки, шаг и прогресс."""
        show_dire = self._settings.get_show_dire()
        self._dire.set_team_visible(show_dire)
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
        """Публичное имя для лаунчера: позиция/прозрачность/флаги."""
        self._apply_settings()

    def _apply_settings(self) -> None:
        """Позиция, прозрачность, click-through — из SettingsService."""
        was_visible = self.isVisible()
        x, y = self._settings.get_overlay_position()
        self.move(int(x), int(y))
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

    def _update_gear_state(self) -> None:
        """Шестерёнка активна только без click-through; иначе — подсказка."""
        locked = bool(self._settings.get_click_through())
        self._gear.setEnabled(not locked)
        self._lock_hint.setVisible(locked)
        self._gear.setToolTip(
            "Настройки: сначала отключите click-through в лаунчере"
            if locked else "Настройки оверлея"
        )
