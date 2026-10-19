"""Сервис драфта 2-2-1 и рекомендации героев. Контракт T-012 (DraftService)."""

import json

from sqlalchemy.orm import Session, sessionmaker

from vetmo.data.models_orm import DraftSessionORM
from vetmo.data.repositories.counter_repo import CounterRepository
from vetmo.data.repositories.draft_repo import DraftRepository
from vetmo.data.repositories.hero_repo import HeroRepository
from vetmo.data.repositories.meta_repo import MetaRepository
from vetmo.data.repositories.settings_repo import SettingsRepository
from vetmo.domain.models import DraftSession, Hero, Pick, Team
from vetmo.domain.rules import is_valid_step, suggest_position, team_for_step

_KEY_PRIORITIES = "position_priorities"
_PRIORITY_BONUS = 10.0


class DraftService:
    """Сценарий драфта: сессии, пики (2-2-1) и рекомендации по позициям."""

    def __init__(
        self, sessionmaker: sessionmaker[Session],
        hero_repo_cls: type = HeroRepository,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._hero_repo_cls = hero_repo_cls

    # --- сессии ---
    def start_session(self) -> DraftSession:
        """Начинает новую сессию драфта."""
        with self._sessionmaker() as session:
            return DraftRepository(session).start_session()

    def _latest_session_id(self, session: Session) -> int | None:
        """Id последней созданной сессии или None."""
        row = (
            session.query(DraftSessionORM)
            .order_by(DraftSessionORM.id.desc())
            .first()
        )
        return row.id if row else None

    def get_state(self, session_id: int | None = None) -> DraftSession:
        """Текущее состояние сессии; без id — последняя (или новая)."""
        with self._sessionmaker() as session:
            repo = DraftRepository(session)
            if session_id is None:
                latest = self._latest_session_id(session)
                if latest is None:
                    return repo.start_session()
                session_id = latest
            state = repo.get_session(session_id)
            if state is None:
                raise ValueError(f"Сессия драфта не найдена: {session_id}")
            return state

    # --- пики ---
    def add_pick(
        self, team: str, position: int, hero_id: int,
        session_id: int | None = None,
    ) -> DraftSession:
        """Пикает команду, продвигает шаг; ошибки — ValueError."""
        with self._sessionmaker() as session:
            repo = DraftRepository(session)
            if session_id is None:
                latest = self._latest_session_id(session)
                session_id = latest if latest is not None else None
            if session_id is not None:
                state = repo.get_session(session_id)
                if state is None:
                    raise ValueError(f"Сессия драфта не найдена: {session_id}")
            else:
                state = repo.start_session()
                session_id = state.id
            step = state.current_step
            if not is_valid_step(step):
                raise ValueError(
                    f"Драфт завершён (draft is finished), шаг: {step}")
            expected_team = team_for_step(step)
            if team != expected_team:
                raise ValueError(
                    f"Сейчас пик команды {expected_team}, а не {team}")
            taken = [p.position for p in state.picks if p.team == team]
            if position in taken:
                raise ValueError(
                    f"Позиция {position} команды {team} уже занята (position taken)")
            picked_heroes = {p.hero_id for p in state.picks}
            if hero_id in picked_heroes:
                raise ValueError(
                    f"Герой {hero_id} уже пикнут (hero already picked)")
            repo.add_pick(session_id, Pick(team=team, position=position, hero_id=hero_id), step)
            loaded = repo.get_session(session_id)
            if loaded is None:
                raise ValueError(f"Сессия драфта не найдена: {session_id}")
            return loaded

    def add_pick_auto(
        self, position: int | None, hero_id: int,
        session_id: int | None = None,
    ) -> DraftSession:
        """Команда — по правилам 2-2-1; position — наименьшая свободная, если None."""
        state = self.get_state(session_id)
        step = state.current_step
        if not is_valid_step(step):
            raise ValueError(f"Драфт завершён (draft is finished), шаг: {step}")
        team = team_for_step(step)
        if position is None:
            taken = [p.position for p in state.picks if p.team == team]
            position = suggest_position(team, taken)
        return self.add_pick(team, position, hero_id, session_id=state.id)

    # --- рекомендации ---
    def _read_priorities(self) -> dict[int, list[int]]:
        """Приоритеты позиций из user_settings."""
        with self._sessionmaker() as session:
            raw = SettingsRepository(session).get(_KEY_PRIORITIES)
            if not raw:
                return {}
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            return {}
        if not isinstance(data, dict):
            return {}
        priorities: dict[int, list[int]] = {}
        for key, ids in data.items():
            try:
                pos = int(key)
            except (TypeError, ValueError):
                continue
            if 1 <= pos <= 5:
                priorities[pos] = [int(h) for h in ids if int(h) >= 1]
        return priorities

    def get_recommendations(
        self, position: int, session_id: int | None = None,
        limit: int = 5,
    ) -> list[tuple[Hero, float]]:
        """[(Hero, score)] по убыванию; без меты/контрпиков — приоритеты и каталог."""
        if not 1 <= position <= 5:
            raise ValueError(f"Позиция вне 1..5: {position}")
        priorities = self._read_priorities()
        with self._sessionmaker() as session:
            heroes = HeroRepository(session).get_all()
            if not heroes:
                return []
            enemy_ids: set[int] = set()
            picked: set[int] = set()
            if session_id is not None:
                state = DraftRepository(session).get_session(session_id)
                if state is not None:
                    picked = {p.hero_id for p in state.picks}
                    if state.picks:
                        own_team: Team = state.picks[-1].team  # noqa: F841
                        enemy_ids = {
                            p.hero_id for p in state.picks
                            if p.team != state.picks[-1].team
                        }
            meta_repo = MetaRepository(session)
            counter_repo = CounterRepository(session)
            candidates: list[tuple[Hero, float]] = []
            for hero in heroes:
                if hero.id in picked:
                    continue
                score = self._score_hero(
                    session, hero, position, enemy_ids,
                    meta_repo, counter_repo, priorities,
                )
                candidates.append((hero, score))
            candidates.sort(key=lambda t: (-t[1], t[0].localized_name))
            return candidates[:limit]

    def _score_hero(
        self, session: Session, hero: Hero, position: int,
        enemy_ids: set[int],
        meta_repo: MetaRepository, counter_repo: CounterRepository,
        priorities: dict[int, list[int]],
    ) -> float:
        """Скоринг героя: мета + контрпики против enemy − enemy контрит + приоритет."""
        score = 0.0
        has_meta = has_counters = False
        meta = meta_repo.get_meta(hero.id)
        if meta is not None:
            score += meta[0]
            has_meta = True
        if enemy_ids:
            for countered_hero, wr_against, _sample in counter_repo.get_hero_counters(hero.id):
                if countered_hero.id in enemy_ids:
                    score += wr_against
                    has_counters = True
            for enemy_counter, wr_against, _sample in counter_repo.get_counters_hero_faces(hero.id):
                if enemy_counter.id in enemy_ids:
                    score -= wr_against
                    has_counters = True
        # Пустая таблица синергий: win_rate_with=0 (данных от API нет).
        if hero.id in priorities.get(position, []):
            score += _PRIORITY_BONUS
        if not (has_meta or has_counters) and not priorities.get(position):
            return 0.0
        return score
