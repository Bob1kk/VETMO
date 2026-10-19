"""Тесты DraftService (T-012): машина состояний 2-2-1 и рекомендации."""

import pytest

from vetmo.data.repositories.hero_repo import HeroRepository
from vetmo.data.repositories.settings_repo import SettingsRepository
from vetmo.domain.models import Hero
from vetmo.services.draft_service import DraftService

HEROES = list(range(100, 110))


def _add_heroes(sessionmaker) -> None:
    """10 героев 100..109 для тестов драфта."""
    with sessionmaker() as session:
        repo = HeroRepository(session)
        for i in HEROES:
            repo.upsert(Hero(id=i, name=f"hero-{i}", localized_name=f"Hero {i}",
                             primary_attr="str", attack_type="Melee",
                             roles=[], icon_url=None, is_validated=True))


@pytest.fixture()
def svc(db) -> DraftService:
    """Драфт-сервис; герои созданы, приоритетов нет."""
    _, sessionmaker = db
    _add_heroes(sessionmaker)
    return DraftService(sessionmaker)


@pytest.fixture()
def svc_full(db) -> DraftService:
    """Как svc + приоритеты позиции 1: [101, 102]."""
    _, sessionmaker = db
    _add_heroes(sessionmaker)
    with sessionmaker() as session:
        SettingsRepository(session).set("position_priorities", '{"1": [101, 102]}')
    return DraftService(sessionmaker)


def test_add_pick_auto_advances_step(svc: DraftService) -> None:
    """add_pick_auto берёт команду из PICK_ORDER и продвигает шаг."""
    state = svc.start_session()
    assert state.current_step == 0
    state = svc.add_pick_auto(None, hero_id=100, session_id=state.id)
    assert state.current_step == 1
    assert state.picks[0].team == "radiant" and state.picks[0].position == 1
    state = svc.add_pick_auto(2, hero_id=101, session_id=state.id)
    assert state.picks[1].team == "radiant" and state.picks[1].position == 2
    state = svc.add_pick_auto(None, hero_id=102, session_id=state.id)
    assert state.picks[2].team == "dire" and state.picks[2].position == 1


def test_add_pick_raises_when_not_your_turn(svc: DraftService) -> None:
    """Пик не в свою команду по очереди -> ValueError."""
    svc.start_session()
    with pytest.raises(ValueError, match="radiant"):
        svc.add_pick("dire", 1, 100)


def test_add_pick_rejects_taken_position(svc: DraftService) -> None:
    """Повторный пик занятой позиции той же команды -> ValueError."""
    svc.start_session()
    svc.add_pick("radiant", 1, 100)
    svc.add_pick("radiant", 2, 101)
    svc.add_pick("dire", 1, 102)
    svc.add_pick("dire", 2, 103)
    with pytest.raises(ValueError, match="занята"):
        svc.add_pick("radiant", 1, 104)


def test_add_pick_rejects_duplicate_hero(svc: DraftService) -> None:
    """Тот же герой второй раз (другой командой) -> ValueError."""
    svc.start_session()
    svc.add_pick("radiant", 1, 100)
    svc.add_pick("radiant", 2, 101)
    with pytest.raises(ValueError, match="пикнут"):
        svc.add_pick("dire", 1, 100)


def test_add_pick_rejects_step_overflow(svc: DraftService) -> None:
    """11-й пик -> ValueError (драфт завершён)."""
    state = svc.start_session()
    for hero_id in HEROES:
        state = svc.add_pick_auto(None, hero_id=hero_id, session_id=state.id)
    assert state.current_step == 10
    with pytest.raises(ValueError, match="заверш"):
        svc.add_pick_auto(None, hero_id=100, session_id=state.id)


def test_get_state_creates_session_if_missing(svc: DraftService) -> None:
    """get_state без сессий создаёт новую."""
    state = svc.get_state(None)
    assert state.id is not None and state.total_picks == 10


def test_recommendations_nonempty_and_sorted(svc_full: DraftService) -> None:
    """Рекомендации без меты: приоритетные первыми, отсортированы по score."""
    recs = svc_full.get_recommendations(1, limit=5)
    assert len(recs) > 0
    scores = [s for _, s in recs]
    assert scores == sorted(scores, reverse=True)
    assert recs[0][0].id == 101  # приоритет позиции 1 -> hero-101
    assert recs[0][1] == 10.0


def test_recommendations_exclude_picked_hero(svc_full: DraftService) -> None:
    """Пикнутый герой не попадает в рекомендации."""
    state = svc_full.start_session()
    state = svc_full.add_pick_auto(None, hero_id=101, session_id=state.id)
    recs = svc_full.get_recommendations(1, session_id=state.id, limit=5)
    ids = [h.id for h, _ in recs]
    assert 101 not in ids
    assert ids[0] == 102  # следующий по приоритету


def test_recommendations_without_priorities(db) -> None:
    """Без приоритетов и меты: непустой список со score 0.0, отсортирован."""
    _, sessionmaker = db
    _add_heroes(sessionmaker)
    service = DraftService(sessionmaker)
    recs = service.get_recommendations(2, limit=5)
    assert [h.id for h, _ in recs] == HEROES[:5]
    assert all(s == 0.0 for _, s in recs)
