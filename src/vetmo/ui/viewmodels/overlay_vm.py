"""OverlayViewModel: рекомендации позиций 1..5 + причины. Без Qt (NFR-005).

Причины рекомендации (по убыванию приоритета):
- «Приоритет позиции N» — герой из пользовательских приоритетов;
- «Контр-пик» — есть пики соперника и счёт вырос против базовой линии;
- «Мета · WR x%» — герой в мета-топе с известным винрейтом;
- «Подбор по позициям» — каталог/роли.
"""

from collections.abc import Callable
from dataclasses import dataclass, field

from vetmo.domain.models import DraftSession, Hero
from vetmo.domain.rules import TOTAL_PICKS
from vetmo.services.draft_service import DraftService
from vetmo.services.news_service import NewsService
from vetmo.services.settings_service import SettingsService

_TEAM_RADIANT = "radiant"
_TEAM_DIRE = "dire"


@dataclass
class OverlayEntry:
    """Одна карточка рекомендации."""

    hero: Hero
    score: float
    reason: str
    win_rate: float | None = None

    def wr_text(self) -> str:
        """Текст винрейта (или пустая строка)."""
        if self.win_rate is None:
            return ""
        return f"WR {self.win_rate:.1f}%"


@dataclass
class OverlaySnapshot:
    """Полный снимок оверлея: шаг драфта, колонки, пикнутые герои."""

    step: int = 0
    total: int = TOTAL_PICKS
    next_team: str = _TEAM_RADIANT
    columns: dict[str, dict[int, list[OverlayEntry]]] = field(
        default_factory=lambda: {_TEAM_RADIANT: {}, _TEAM_DIRE: {}},
    )
    picked: dict[str, dict[int, Hero | None]] = field(
        default_factory=lambda: {_TEAM_RADIANT: {}, _TEAM_DIRE: {}},
    )

    def step_text(self) -> str:
        """«Шаг драфта: X/10 — сейчас пикает Radiant»."""
        return f"Шаг драфта: {self.step}/{self.total} — пикает {self.next_team}"


class OverlayViewModel:
    """Собирает данные для OverlayWindow через сервисы (никакого SQL)."""

    def __init__(
        self,
        draft_service: DraftService,
        settings_service: SettingsService,
        news_service: NewsService,
        hero_lookup: Callable[[int], Hero | None] | None = None,
    ) -> None:
        self._draft = draft_service
        self._settings = settings_service
        self._news = news_service
        self._hero_lookup = hero_lookup

    # --- одиночная позиция (публичный контракт refresh) ---
    def refresh(
        self, position: int, session_id: int | None = None, limit: int = 5,
    ) -> list[tuple[Hero, float, str]]:
        """[(Hero, score, причина)] для позиции — без контекста драфта."""
        recs = self._draft.get_recommendations(position, session_id, limit)
        priorities = self._settings.get_position_priorities()
        meta_wr = self._meta_win_rates()
        return [
            (hero, score, _classify_reason(
                position, hero, score, {}, set(), priorities, meta_wr,
            ))
            for hero, score in recs
        ]

    # --- полный снимок (worker-поток) ---
    def compute_all(
        self, session_id: int | None = None, limit: int = 3,
    ) -> OverlaySnapshot:
        """Снимок обеих колонок: рекомендации, пикнутые, шаг драфта."""
        state = self._draft.get_state(session_id)
        meta_wr = self._meta_win_rates()
        snapshot = OverlaySnapshot(
            step=state.current_step,
            total=state.total_picks,
            next_team=_next_team(state),
        )
        opponents = _opponent_hero_ids(state)
        priorities = self._settings.get_position_priorities()
        for team in (_TEAM_RADIANT, _TEAM_DIRE):
            taken = [p.position for p in state.picks if p.team == team]
            for position in range(1, 6):
                snapshot.picked[team][position] = (
                    self._picked_hero(state, team, position)
                )
                if position in taken:
                    continue  # позиция занята — карточку рекомендаций не пикаем
                snapshot.columns[team][position] = self._entries_for(
                    position, state, opponents, priorities, meta_wr, limit,
                )
        return snapshot

    # --- внутренние ---
    def _entries_for(
        self,
        position: int,
        state: DraftSession,
        opponents: set[int],
        priorities: dict[int, list[int]],
        meta_wr: dict[int, float],
        limit: int,
    ) -> list[OverlayEntry]:
        """Рекомендации позиции с причинами (приоритет > контр-пик > мета)."""
        recs = self._draft.get_recommendations(position, state.id, limit)
        baseline: dict[int, float] = {}
        if opponents:
            base = self._draft.get_recommendations(
                position, None, limit=_LARGE_LIMIT,
            )
            baseline = {hero.id: score for hero, score in base}
        entries: list[OverlayEntry] = []
        for hero, score in recs:
            reason = _classify_reason(
                position, hero, score, baseline, opponents,
                priorities, meta_wr,
            )
            entries.append(OverlayEntry(
                hero=hero, score=score, reason=reason,
                win_rate=meta_wr.get(hero.id),
            ))
        return entries

    def _meta_win_rates(self) -> dict[int, float]:
        """hero_id -> win_rate из мета-топа (для подписи WR на карточке)."""
        try:
            summary = self._news.get_meta_summary(limit=15)
        except Exception:  # noqa: BLE001 — мета не обязательна для оверлея
            return {}
        return {
            hero.id: float(win_rate) for hero, win_rate, _pick in summary.top
        }

    def _picked_hero(
        self, state: DraftSession, team: str, position: int,
    ) -> Hero | None:
        """Пикнутый герой позиции команды или None."""
        pick = next(
            (p for p in state.picks
             if p.team == team and p.position == position),
            None,
        )
        if pick is None or self._hero_lookup is None:
            return None
        try:
            return self._hero_lookup(pick.hero_id)
        except Exception:  # noqa: BLE001 — каталог мог измениться
            return None


_LARGE_LIMIT = 200


def _next_team(state: DraftSession) -> str:
    """Команда, которая пикает на текущем шаге (по правилам 2-2-1)."""
    from vetmo.domain.rules import team_for_step

    try:
        return team_for_step(state.current_step)
    except ValueError:
        return _TEAM_RADIANT


def _opponent_hero_ids(state: DraftSession) -> set[int]:
    """Id героев обеих команд, кроме героев команды последнего пика."""
    if not state.picks:
        return set()
    last_team = state.picks[-1].team
    return {p.hero_id for p in state.picks if p.team != last_team}


def _classify_reason(
    position: int,
    hero: Hero,
    score: float,
    baseline: dict[int, float],
    opponents: set[int],
    priorities: dict[int, list[int]],
    meta_wr: dict[int, float],
) -> str:
    """Выбор текста причины карточки."""
    if hero.id in priorities.get(position, []):
        return "Приоритет позиции"
    if opponents and hero.id in baseline:
        delta = score - baseline[hero.id]
        if delta > _COUNTER_DELTA:
            return "Контр-пик"
    wr = meta_wr.get(hero.id)
    if wr is not None:
        return f"Мета · WR {wr:.1f}%"
    return "Подбор по позициям"


_COUNTER_DELTA = 0.5
