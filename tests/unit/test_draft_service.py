"""Тесты DraftService (T-012): машина состояний 2-2-1 и рекомендации."""

import pytest

from vetmo.data.repositories.counter_repo import CounterRepository
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


def test_recommendations_for_none_state_is_baseline(
    svc_full: DraftService,
) -> None:
    """state=None — базовая линия: пики не учитываются (Δ контр-пика)."""
    state = svc_full.start_session()
    state = svc_full.add_pick_auto(None, hero_id=101, session_id=state.id)

    baseline = [
        hero.id for hero, _ in svc_full.get_recommendations_for(
            None, 1, limit=5)
    ]
    current = [
        hero.id for hero, _ in svc_full.get_recommendations_for(
            state, 1, limit=5)
    ]

    assert 101 in baseline  # без состояния герой ещё «свободен»
    assert 101 not in current


def test_recommendations_without_priorities(db) -> None:
    """Без приоритетов и меты: непустой список со score 0.0, отсортирован."""
    _, sessionmaker = db
    _add_heroes(sessionmaker)
    service = DraftService(sessionmaker)
    recs = service.get_recommendations(2, limit=5)
    assert [h.id for h, _ in recs] == HEROES[:5]
    assert all(s == 0.0 for _, s in recs)


def test_recommendations_position_fit(db) -> None:
    """Ролевой фит влияет: Carry первый на pos 1 с 5.0, на pos 5 — 0.0."""
    from vetmo.domain.models import Hero as H
    _, sessionmaker = db
    with sessionmaker() as session:
        repo = HeroRepository(session)
        repo.upsert(H(id=200, name="carry-hero", localized_name="Carry A",
                      primary_attr="agi", attack_type="Melee",
                      roles=["Carry", "Escape"], icon_url=None))
        repo.upsert(H(id=201, name="hard-support-hero", localized_name="Support B",
                      primary_attr="int", attack_type="Ranged",
                      roles=["Hard Support"], icon_url=None))
    service = DraftService(sessionmaker)
    pos1 = dict((h.id, s) for h, s in service.get_recommendations(1, limit=10))
    assert pos1[200] == 5.0   # фит 1.0 * вес 5.0
    assert pos1[201] == 0.0   # hard_support не роль позиции 1
    pos5 = dict((h.id, s) for h, s in service.get_recommendations(5, limit=10))
    assert pos5[201] == 5.0   # 'Hard Support' — первичная роль pos 5
    assert pos5[200] == 0.0   # carry не вылезает на позицию 5
    # сортировка: carry впереди на pos1, саппорт впереди на pos5
    assert service.get_recommendations(1, limit=10)[0][0].id == 200
    assert service.get_recommendations(5, limit=10)[0][0].id == 201


def test_recommendations_supporting_role_partial_fit(db) -> None:
    """Поддерживающая роль даёт 0.6 * 5.0 = 3.0."""
    from vetmo.domain.models import Hero as H
    _, sessionmaker = db
    with sessionmaker() as session:
        HeroRepository(session).upsert(
            H(id=202, name="durable-hero", localized_name="Durable C",
              primary_attr="str", attack_type="Melee",
              roles=["Durable"], icon_url=None))
    service = DraftService(sessionmaker)
    pos3 = dict((h.id, s) for h, s in service.get_recommendations(3, limit=10))
    assert pos3[202] == 3.0  # 0.6 (поддерживающая) * 5.0


def test_recommendations_use_settings_service_priorities(db) -> None:
    """DraftService берёт приоритеты из SettingsService, если привязан."""
    from vetmo.services.settings_service import SettingsService
    _, sessionmaker = db
    _add_heroes(sessionmaker)
    settings_service = SettingsService(sessionmaker)
    settings_service.set_position_priorities({1: [104]})
    service = DraftService(sessionmaker, settings_service=settings_service)
    recs = service.get_recommendations(1, limit=3)
    assert recs[0][0].id == 104
    assert recs[0][1] == 10.0


def test_recommendations_use_enemy_of_team_on_clock(db) -> None:
    """Шаг 2: пикает Dire — контрпики считаются против героев Radiant.

    Регрессия: enemy_ids строился от команды последнего пика (Radiant),
    поэтому на шаге Dire «соперниками» оказывались его же будущие пики.
    """
    _, sessionmaker = db
    _add_heroes(sessionmaker)
    with sessionmaker() as session:
        counters = CounterRepository(session)
        counters.upsert(108, 105, 60.0, 1000)
        counters.upsert(109, 106, 60.0, 1000)
    service = DraftService(sessionmaker)
    state = service.start_session()
    state = service.add_pick_auto(1, hero_id=105, session_id=state.id)
    state = service.add_pick_auto(2, hero_id=106, session_id=state.id)
    assert state.current_step == 2
    recs = service.get_recommendations(1, session_id=state.id, limit=2)
    assert [hero.id for hero, _ in recs] == [108, 109]


def test_recommendations_team_perspective(db) -> None:
    """team= переключает перспективу: контрпики против соперника колонки."""
    _, sessionmaker = db
    _add_heroes(sessionmaker)
    with sessionmaker() as session:
        counters = CounterRepository(session)
        counters.upsert(107, 100, 60.0, 1000)
        counters.upsert(108, 101, 60.0, 1000)
        counters.upsert(109, 102, 60.0, 1000)
    service = DraftService(sessionmaker)
    state = service.start_session()
    state = service.add_pick_auto(1, hero_id=100, session_id=state.id)
    state = service.add_pick_auto(2, hero_id=101, session_id=state.id)
    state = service.add_pick_auto(1, hero_id=102, session_id=state.id)

    dire = service.get_recommendations(
        1, session_id=state.id, limit=2, team="dire")
    assert [hero.id for hero, _ in dire] == [107, 108]
    # Без team — колонка команды на часах (Dire).
    default = service.get_recommendations(1, session_id=state.id, limit=2)
    assert [hero.id for hero, _ in default] == [107, 108]

    radiant = service.get_recommendations(
        1, session_id=state.id, limit=2, team="radiant")
    assert [hero.id for hero, _ in radiant] == [109, 103]


def test_matchup_tooltip(db) -> None:
    """get_matchup_tooltip: strong/weak с Δ от 50% и фильтром выборки >= 100."""
    _, sessionmaker = db
    _add_heroes(sessionmaker)
    with sessionmaker() as session:
        counters = CounterRepository(session)
        counters.upsert(100, 101, 57.5, 1000)  # 100 силён против 101
        counters.upsert(102, 100, 54.0, 1000)  # 102 контрит 100
        counters.upsert(103, 100, 70.0, 50)    # выборка < 100 — мимо
    service = DraftService(sessionmaker)
    assert service.get_matchup_tooltip(100) == (
        [("Hero 101", 7.5)],
        [("Hero 102", -4.0)],
    )
    assert service.get_matchup_tooltip(104) is None
