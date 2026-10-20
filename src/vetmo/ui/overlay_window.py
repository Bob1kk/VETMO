"""Окно оверлея: borderless, always-on-top, прозрачный фон, click-through (T-011).

Не крадёт фокус у Dota 2 (Review Focus #2): Qt.Tool +
WA_ShowWithoutActivating + NoFocus; при click-through мышь проходит
насквозь. Позиция/прозрачность/флаги читаются из SettingsService.
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from vetmo.services.settings_service import SettingsService
from vetmo.ui.viewmodels.overlay_vm import OverlaySnapshot
from vetmo.ui.widgets.hero_card import HeroCard

_TEAM_TITLES = (("radiant", "Radiant"), ("dire", "Dire"))
_CARDS_PER_POSITION = 2


class OverlayColumn(QFrame):
    """Колонка команды: заголовок + 5 позиций с карточками героев."""

    def __init__(self, team: str, title: str,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("overlayPanel")
        self._team = team
        self._cards: dict[int, list[HeroCard]] = {}

        header = QLabel(title, self)
        header.setObjectName("overlayTitle")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 10)
        layout.setSpacing(3)
        layout.addWidget(header)

        for position in range(1, 6):
            pos_label = QLabel(f"Позиция {position}", self)
            pos_label.setObjectName("overlayPosLabel")
            layout.addWidget(pos_label)
            cards = [HeroCard(self) for _ in range(_CARDS_PER_POSITION)]
            for card in cards:
                card.setObjectName("overlayCard")
                card.setSizePolicy(
                    QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
                card.setMaximumHeight(52)
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
        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 2)
        title = QLabel("VETMO OVERLAY", self)
        title.setObjectName("overlayTitle")
        self._step = QLabel("Шаг драфта: 0/10", self)
        self._step.setObjectName("overlayStep")
        self._step.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        header_row.addWidget(title)
        header_row.addStretch(1)
        header_row.addWidget(self._step)

        self._radiant = OverlayColumn("radiant", "Radiant", self)
        self._dire = OverlayColumn("dire", "Dire", self)
        columns = QHBoxLayout()
        columns.setContentsMargins(0, 0, 0, 0)
        columns.setSpacing(8)
        columns.addWidget(self._radiant)
        columns.addWidget(self._dire)

        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(12, 10, 12, 12)
        panel_layout.setSpacing(6)
        panel_layout.addLayout(header_row)
        panel_layout.addLayout(columns)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(panel)

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
        """Применяет снимок OverlayViewModel: колонки и шаг драфта."""
        show_dire = self._settings.get_show_dire()
        self._dire.set_team_visible(show_dire)
        self._radiant.fill(snapshot)
        if show_dire:
            self._dire.fill(snapshot)
        self._step.setText(snapshot.step_text())
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
        if was_visible and not self.isVisible():
            self.show()
            self.adjustSize()
