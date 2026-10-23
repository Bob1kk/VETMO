"""Сервис драфта 2-2-1 и рекомендации героев. Контракт T-012 (DraftService)."""

from sqlalchemy.orm import Session, sessionmaker

from vetmo.data.models_orm import DraftSessionORM
from vetmo.data.repositories.counter_repo import CounterRepository
from vetmo.data.repositories.draft_repo import DraftRepository
from vetmo.data.repositories.hero_repo import HeroRepository
from vetmo.data.repositories.meta_repo import MetaRepository
from vetmo.domain.models import DraftSession, Hero, Pick, Team
from vetmo.domain.rules import (
    is_valid_step,
    position_fit,
    suggest_position,
    team_for_step,
)

_POSITION_FIT_WEIGHT = 5.0
_TOOLTIP_ROWS = 5


def _team_on_clock(state: DraftSession) -> Team | None:
    """Команда, которая пикает на текущем шаге, или None (драфт завершён)."""
    try:
        return team_for_step(state.current_step)
    except ValueError:
        return None


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
                assert state.id is not None, "commit не выставил id сессии"
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
    def get_recommendations(
        self, position: int, session_id: int | None = None,
        limit: int = 5, team: Team | None = None,
    ) -> list[tuple[Hero, float]]:
        """[(Hero, score)] по убыванию; без меты/контрпиков — каталог и фит.

        team — перспектива (чья колонка рекомендаций); по умолчанию команда,
        которая пикает на текущем шаге. Контрпики считаются против соперника
        именно этой команды.
        """
        if not 1 <= position <= 5:
            raise ValueError(f"Позиция вне 1..5: {position}")
        if limit <= 0:
            return []
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
                    perspective = team or _team_on_clock(state)
                    if perspective is not None:
                        enemy_ids = {
                            p.hero_id for p in state.picks
                            if p.team != perspective
                        }
            meta_repo = MetaRepository(session)
            counter_repo = CounterRepository(session)
            candidates: list[tuple[Hero, float]] = []
            for hero in heroes:
                if hero.id in picked:
                    continue
                score = self._score_hero(
                    session, hero, position, enemy_ids,
                    meta_repo, counter_repo,
                )
                candidates.append((hero, score))
            candidates.sort(key=lambda t: (-t[1], t[0].localized_name))
            return candidates[:limit]

    def get_recommendations_for(
        self, state: DraftSession | None, position: int,
        limit: int = 5, team: Team | None = None,
    ) -> list[tuple[Hero, float]]:
        """Рекомендации по уже загруженному состоянию (без повторного чтения).

        ``state=None`` — базовая линия без пиков (контр-пик Δ в оверлее).
        """
        return self.get_recommendations(
            position,
            state.id if state is not None else None,
            limit=limit,
            team=team,
        )

    def get_matchup_tooltip(
        self, hero_id: int,
    ) -> tuple[list[tuple[str, float]], list[tuple[str, float]]] | None:
        """(strong, weak) для rich-tooltip: [(имя, Δ winrate), ...] или None.

        Δ считается от 50%: у weak отрицательная (герой проигрывает врагу).
        None — контрпиков с достоверной выборкой нет.
        """
        with self._sessionmaker() as session:
            repo = CounterRepository(session)
            strong = repo.top_advantages(hero_id, limit=_TOOLTIP_ROWS)
            weak = repo.top_disadvantages(hero_id, limit=_TOOLTIP_ROWS)
        if not strong and not weak:
            return None
        return (
            [(hero.localized_name or hero.name, round(wr - 50.0, 2))
             for hero, wr in strong],
            [(hero.localized_name or hero.name, round(50.0 - wr, 2))
             for hero, wr in weak],
        )

    def _score_hero(
        self, session: Session, hero: Hero, position: int,
        enemy_ids: set[int],
        meta_repo: MetaRepository, counter_repo: CounterRepository,
    ) -> float:
        """Скоринг: мета + контрпики − enemy контрит + position_fit."""
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
        # Ролевой фит: 1.0 первичная роль, 0.6 поддерживающая (см. rules.POSITION_ROLES).
        # Вес до +5.0: мета/контрпики доминируют, carry не вылезает на pos 5.
        fit = position_fit(tuple(hero.roles), position)
        score += fit * _POSITION_FIT_WEIGHT
        # Фолбэк: данных (мета/контрпики) нет и фит нулевой — мусор не выдаём.
        if not (has_meta or has_counters) and fit == 0.0:
            return 0.0
        return score
