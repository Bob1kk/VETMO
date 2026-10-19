"""Карточка героя-рекомендации: иконка, имя, WR, причина (T-011/R2).

R2 (задача B): рич-тултип контрпиков по hover — лениво, один запрос на
карточку, запрос уходит в QThreadPool (UI не блокируется). Иконки:
локальный кэш assets/cache/icons/{hero_id}.png первый, потом CDN.
"""

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QCursor, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from vetmo.domain.models import Hero
from vetmo.ui.widgets.hero_icon import placeholder_pixmap, resolve_icon, scale_icon
from vetmo.ui.widgets.icon_fetcher import icon_fetcher
from vetmo.ui.widgets.matchup import format_matchup_tooltip
from vetmo.ui.workers import start_worker

_ICON_SIZE = 34


class HeroCard(QFrame):
    """Карточка: [иконка 34px] Имя / WR справа / причина снизу."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("heroCard")
        self._icon = QLabel(self)
        self._icon.setFixedSize(QSize(_ICON_SIZE, _ICON_SIZE))
        self._icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._name = QLabel(self)
        self._name.setObjectName("cardName")
        self._reason = QLabel(self)
        self._reason.setObjectName("cardReason")
        self._wr = QLabel(self)
        self._wr.setObjectName("cardWr")
        self._wr.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._currently_requested: str | None = None

        # матчапы (задача B): ленивый тултип по hover
        self._matchup_loader = None
        self._hero: Hero | None = None
        self._matchup_done: set[int] = set()
        self._matchup_pending: set[int] = set()

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(8)
        top.addWidget(self._icon, 0, Qt.AlignmentFlag.AlignTop)
        text_column = QVBoxLayout()
        text_column.setContentsMargins(0, 0, 0, 0)
        text_column.setSpacing(1)
        info_line = QHBoxLayout()
        info_line.setContentsMargins(0, 0, 0, 0)
        info_line.addWidget(self._name, 1)
        info_line.addWidget(self._wr, 0)
        text_column.addLayout(info_line)
        text_column.addWidget(self._reason)
        top.addLayout(text_column, 1)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.addLayout(top, 1)

        # мягкая тень карточки (задача D, дешёвый способ)
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(12)
        shadow.setOffset(0, 2)
        shadow.setColor(QColor(0, 0, 0, 80))
        self.setGraphicsEffect(shadow)

        icon_fetcher().loaded.connect(self._on_icon_loaded)
        self.set_empty()

    # --- публичный API ---
    def set_empty(self, message: str = "Нет рекомендаций") -> None:
        """Пустая карточка: нейтральный плейсхолдер и подпись."""
        self._hero = None
        self._currently_requested = None
        self._apply(placeholder_pixmap("—"), "", message, "", message)

    def show_hero(
        self, hero: Hero, reason: str = "", wr_text: str = "",
    ) -> None:
        """Показывает героя (иконка локально/из сети, имя, WR, причина)."""
        self._hero = hero
        pixmap, url = resolve_icon(hero.id, self._hero_name(hero), hero.icon_url)
        tooltip = reason or self._hero_name(hero)
        self._apply(
            pixmap,
            self._hero_name(hero),
            reason,
            wr_text,
            tooltip,
        )
        if url:
            self._currently_requested = url
            icon_fetcher().fetch(url)

    def set_matchup_loader(self, loader) -> None:
        """loader(hero_id) -> (strong, weak) | None — вызывается в worker."""
        self._matchup_loader = loader

    def set_matchup_tooltip(
        self, strong: list[tuple[str, float]], weak: list[tuple[str, float]],
    ) -> None:
        """Рич-тултип «Силён против / Слаб против» (контракт задачи B)."""
        name = self._hero_name(self._hero) if self._hero else ""
        html = format_matchup_tooltip(name, strong, weak)
        if html is None:
            return
        if self._hero is not None:
            self._matchup_done.add(self._hero.id)
            self._matchup_pending.discard(self._hero.id)
        self.setToolTip(html)
        if self.underMouse():
            QToolTip.showText(QCursor.pos(), html, self)

    # --- внутренние ---
    @staticmethod
    def _hero_name(hero: Hero | None) -> str:
        if hero is None:
            return ""
        return hero.localized_name or hero.name

    def _apply(
        self, pixmap: QPixmap, name: str, reason: str,
        wr_text: str, tooltip: str,
    ) -> None:
        self._icon.setPixmap(scale_icon(pixmap, _ICON_SIZE))
        self._name.setText(name)
        self._reason.setText(reason)
        self._wr.setText(wr_text)
        self.setToolTip(tooltip)

    def enterEvent(self, event) -> None:  # noqa: N802 — Qt API
        """Hover: лениво считаем матчапы (1 запрос на карточку, worker)."""
        self._maybe_request_matchup()
        super().enterEvent(event)

    def _maybe_request_matchup(self) -> None:
        hero = self._hero
        if self._matchup_loader is None or hero is None:
            return
        if hero.id in (self._matchup_done | self._matchup_pending):
            return
        self._matchup_pending.add(hero.id)
        start_worker(
            self._matchup_loader, hero.id,
            on_done=self._matchup_ready,
            on_fail=lambda _msg, done=hero.id: self._matchup_fail(done),
        )

    def _matchup_ready(self, result: object) -> None:
        hero = self._hero
        if hero is None or not isinstance(result, tuple) or len(result) != 2:
            if hero is not None:
                self._matchup_pending.discard(hero.id)
                self._matchup_done.add(hero.id)
            return
        self.set_matchup_tooltip(result[0], result[1])

    def _matchup_fail(self, hero_id: int) -> None:
        self._matchup_pending.discard(hero_id)
        self._matchup_done.add(hero_id)

    def _on_icon_loaded(self, url: str, pixmap: QPixmap) -> None:
        """Обновляет иконку только своей карточки (пока URL жив)."""
        if url != self._currently_requested:
            return
        self._currently_requested = None
        if pixmap.isNull():
            return
        self._icon.setPixmap(scale_icon(pixmap, _ICON_SIZE))
