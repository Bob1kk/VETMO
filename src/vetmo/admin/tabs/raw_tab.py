"""Вкладка «Сырые данные STRATZ»: произвольный запрос и JSON-viewer (T-108)."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from vetmo.admin.tabs.common import JsonViewer
from vetmo.domain.rank_brackets import (
    ALL_BRACKET,
    BASIC_BRACKET_BY_RANK,
    BASIC_BRACKETS,
    basic_bracket_for_rank,
    basic_bracket_label,
)
from vetmo.services.stratz_client import (
    BAN_DAY_QUERY,
    CONSTANTS_QUERY,
    MATCHUP_QUERY,
    WIN_DAY_QUERY,
)
from vetmo.ui.workers import start_worker

if TYPE_CHECKING:
    from vetmo.admin.context import AdminContext

_QUERIES: tuple[tuple[str, str], ...] = (
    ("gameVersions — патчи", "gameVersions"),
    ("winDay — мета по дням", "winDay"),
    ("banDay — баны", "banDay"),
    ("matchUp — матчапы героя", "matchUp"),
)

_QUERY_TEXT: dict[str, str] = {
    "gameVersions": CONSTANTS_QUERY,
    "winDay": WIN_DAY_QUERY,
    "banDay": BAN_DAY_QUERY,
    "matchUp": MATCHUP_QUERY,
}

_RANKS: tuple[tuple[int, str], ...] = (
    (1, "1 — Рекрут"),
    (2, "2 — Страж"),
    (3, "3 — Рыцарь"),
    (4, "4 — Герой"),
    (5, "5 — Легенда"),
    (6, "6 — Властелин"),
    (7, "7 — Божество"),
    (8, "8 — Титан"),
)


class RawTab(QWidget):
    """Ручной GraphQL-запрос к STRATZ без записи в БД."""

    status_message = Signal(str)

    def __init__(self, context: AdminContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = context
        self._busy = False
        self._build_ui()
        self._update_params()

    # ---------------------------------------------------------------- UI --
    def _build_ui(self) -> None:
        title = QLabel("Сырые данные STRATZ", self)
        title.setObjectName("h1")
        subtitle = QLabel(
            "Запрос выполняется в фоне. Токен не показывается и не логируется.",
            self,
        )
        subtitle.setObjectName("muted")
        subtitle.setWordWrap(True)

        self._query = QComboBox(self)
        self._query.setObjectName("filterCombo")
        for label, key in _QUERIES:
            self._query.addItem(label, key)

        self._rank = QComboBox(self)
        self._rank.setObjectName("filterCombo")
        self._rank.addItem("Все ранги", 0)
        for value, label in _RANKS:
            self._rank.addItem(label, value)

        self._position = QComboBox(self)
        self._position.setObjectName("filterCombo")
        self._position.addItem("Все позиции", 0)
        for value in range(1, 6):
            self._position.addItem(f"Позиция {value}", value)

        self._hero = QSpinBox(self)
        self._hero.setRange(1, 200)
        self._hero.setValue(1)
        self._hero.setToolTip("ID героя Dota 2 (для banDay и matchUp)")

        self._bracket = QComboBox(self)
        self._bracket.setObjectName("filterCombo")
        self._bracket.addItem("Авто (по рангу)", None)
        self._bracket.addItem(basic_bracket_label(ALL_BRACKET), ALL_BRACKET)
        for bracket in BASIC_BRACKETS:
            self._bracket.addItem(basic_bracket_label(bracket), bracket)

        self._run_button = QPushButton("Выполнить", self)
        self._run_button.setObjectName("primary")
        self._run_button.clicked.connect(self._execute)

        self._status = QLabel("Готово", self)
        self._status.setObjectName("mutedSmall")

        self._viewer = JsonViewer(self)

        first = QHBoxLayout()
        first.setSpacing(8)
        first.addWidget(QLabel("Запрос:", self))
        first.addWidget(self._query, 1)
        first.addWidget(self._run_button)

        second = QHBoxLayout()
        second.setSpacing(8)
        second.addWidget(QLabel("Ранг:", self))
        second.addWidget(self._rank)
        second.addWidget(QLabel("Позиция:", self))
        second.addWidget(self._position)
        second.addWidget(QLabel("ID героя:", self))
        second.addWidget(self._hero)
        second.addWidget(QLabel("Срез:", self))
        second.addWidget(self._bracket)
        second.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addLayout(first)
        layout.addLayout(second)
        layout.addWidget(self._status)
        layout.addWidget(self._viewer, 1)

        self._query.currentIndexChanged.connect(self._update_params)

    def _update_params(self) -> None:
        """Включает только параметры, которые понимает выбранный запрос."""
        key = str(self._query.currentData())
        is_win = key == "winDay"
        is_ban = key == "banDay"
        is_matchup = key == "matchUp"
        self._rank.setEnabled(is_win or is_matchup)
        self._position.setEnabled(is_win)
        self._hero.setEnabled(is_ban or is_matchup)
        self._bracket.setEnabled(is_matchup)

    # ------------------------------------------------------------ запросы --
    def _effective_bracket(self) -> str | None:
        """Явный срез из комбо или группа, выведенная из ранга."""
        explicit = self._bracket.currentData()
        if explicit:
            return str(explicit)
        rank = int(self._rank.currentData() or 0)
        if rank > 0:
            return basic_bracket_for_rank(rank)
        return None

    def _variables(self, key: str) -> dict[str, Any]:
        """Собирает переменные GraphQL под выбранный запрос."""
        rank = int(self._rank.currentData() or 0)
        position = int(self._position.currentData() or 0)
        hero_id = int(self._hero.value())

        if key == "winDay":
            variables: dict[str, Any] = {"take": 3000}
            bracket = BASIC_BRACKET_BY_RANK.get(rank)
            if bracket:
                variables["bracketIds"] = [bracket]
            if position > 0:
                variables["positionIds"] = [f"POSITION_{position}"]
            return variables
        if key == "banDay":
            return {
                "heroId": hero_id,
                "take": 30,
                "groupByDay": True,
                "groupByRank": True,
            }
        if key == "matchUp":
            variables = {"heroIds": [hero_id], "take": 100}
            bracket = self._effective_bracket()
            if bracket:
                variables["bracketIds"] = [bracket]
            return variables
        return {}

    def _execute(self) -> None:
        if self._busy:
            return
        key = str(self._query.currentData())
        query = _QUERY_TEXT[key]
        variables = self._variables(key)
        self._busy = True
        self._run_button.setEnabled(False)
        self._status.setStyleSheet("")
        self._status.setText("Выполняется…")
        self.status_message.emit(f"STRATZ: выполняем {key}…")

        def job() -> tuple[dict[str, Any], float]:
            started = time.perf_counter()
            data = self._ctx.client.execute(query, variables)
            return data, time.perf_counter() - started

        def done(result: tuple[dict[str, Any], float]) -> None:
            data, elapsed = result
            self._busy = False
            self._run_button.setEnabled(True)
            self._viewer.set_data(data)
            self._status.setText(f"HTTP 200 · {elapsed:.2f} с · {key}")
            self._status.setStyleSheet("color: #43C59E;")
            self.status_message.emit(f"STRATZ: {key} выполнен за {elapsed:.2f} с")

        def fail(message: str) -> None:
            self._busy = False
            self._run_button.setEnabled(True)
            self._viewer.set_data({"error": message})
            self._status.setText(f"Ошибка: {message}")
            self._status.setStyleSheet("color: #E35D6A;")
            self.status_message.emit(f"STRATZ: ошибка ({message})")

        start_worker(job, on_done=done, on_fail=fail)

    # ------------------------------------------------------------ служебное --
    def is_busy(self) -> bool:
        """Идёт ли запрос (для смоук-тестов)."""
        return self._busy

    def viewer_text(self) -> str:
        """Текст JSON-viewer'а (для смоук-тестов)."""
        return self._viewer.toPlainText()

    def shutdown(self) -> None:
        """Запросы идут через QThreadPool; отменять нечего."""


__all__ = ["RawTab"]
