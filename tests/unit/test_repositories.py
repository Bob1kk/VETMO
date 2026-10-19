"""Тесты остальных репозиториев: мета, контрпики, синергии, настройки, драфт (T-005)."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from vetmo.data.db import create_db, migrate
from vetmo.data.repositories.counter_repo import CounterRepository
from vetmo.data.repositories.draft_repo import DraftRepository
from vetmo.data.repositories.hero_repo import HeroRepository
from vetmo.data.repositories.meta_repo import MetaRepository
from vetmo.data.repositories.settings_repo import SettingsRepository
from vetmo.data.repositories.synergy_repo import SynergyRepository
from vetmo.domain.models import Hero, Pick


@pytest.fixture()
def session(tmp_path: Path) -> Iterator[Session]:
    """Временная файловая SQLite с применённой миграцией."""
    db_path = (tmp_path / "test.db").as_posix()
    engine, sessionmaker = create_db(f"sqlite:///{db_path}")
    migrate(engine, f"sqlite:///{db_path}")
    s = sessionmaker()
    yield s
    s.close()
    engine.dispose()


@pytest.fixture()
def heroes(session: Session) -> list[Hero]:
    """Герои 1..3 для тестов связей."""
    repo = HeroRepository(session)
    result = [
        Hero(id=i, name=f"hero-{i}", localized_name=f"Hero {i}",
             primary_attr="str", attack_type="Melee", roles=[], icon_url=None)
        for i in (1, 2, 3)
    ]
    for h in result:
        repo.upsert(h)
    return result


def test_settings_repo_save_and_load(session: Session) -> None:
    """SettingsRepository: set/get + перезапись (ON CONFLICT)."""
    repo = SettingsRepository(session)
    assert repo.get("overlay.opacity") is None
    repo.set("overlay.opacity", "0.85")
    assert repo.get("overlay.opacity") == "0.85"
    repo.set("overlay.opacity", "0.5")
    assert repo.get("overlay.opacity") == "0.5"
    assert repo.get("nope") is None


def test_counter_repo_upsert_dedup(session: Session, heroes: list[Hero]) -> None:
    """CounterRepository: повторный upsert по паре обновляет, без дублей."""
    repo = CounterRepository(session)
    repo.upsert(1, 2, 45.0, 1000)
    repo.upsert(1, 2, 47.5, 1200)
    repo.upsert(2, 1, 55.0, 800)
    faces = repo.get_counters_hero_faces(1)  # кто контрит героя 1 -> (2, 55.0)
    assert faces == [(heroes[1], 55.0, 800)]
    counters = repo.get_hero_counters(1)  # кого контрит 1 -> (2, 47.5/55? нет: 45->47.5)
    assert len(counters) == 1
    assert counters[0][0].id == 2
    assert counters[0][1] == 47.5


def test_synergy_repo_upsert_and_list(session: Session, heroes: list[Hero]) -> None:
    """SynergyRepository: upsert + get_synergies."""
    repo = SynergyRepository(session)
    repo.upsert(1, 3, 58.0, 900)
    repo.upsert(1, 3, 60.0, 950)  # дедуп
    syn = repo.get_synergies(1)
    assert len(syn) == 1
    assert syn[0][0].id == 3
    assert syn[0][1] == 60.0
    assert repo.get_synergies(2) == []


def test_meta_repo_requires_patch_and_dedup(session: Session, heroes: list[Hero]) -> None:
    """MetaRepository: дедуп по patch+hero+tier, дельты, get_top_meta (MetaRow)."""
    patch_id = MetaRepository.ensure_patch(session, "7.54", None, "тест")
    repo = MetaRepository(session)
    repo.upsert(patch_id, 1, 52.3, 8.1)
    assert repo.get_meta(1) == (52.3, 8.1)
    repo.upsert(patch_id, 1, 53.0, 8.5)  # дедуп по patch+hero(tier=None)
    top = repo.get_top_meta(limit=10)
    assert len(top) == 1
    row = top[0]
    assert row.hero_id == 1 and row.win_rate == 53.0 and row.pick_rate == 8.5
    assert row.delta_win == 0.7 and row.delta_pick == 0.4  # дельты vs прежней строки
    assert repo.get_meta(1) == (53.0, 8.5)


def test_draft_repo_full_cycle(session: Session, heroes: list[Hero]) -> None:
    """DraftRepository: start -> add_pick -> get_session/get_picks -> finish."""
    repo = DraftRepository(session)
    dsession = repo.start_session()
    assert dsession.id is not None and dsession.current_step == 0 \
        and dsession.total_picks == 10

    repo.add_pick(dsession.id, Pick(team="radiant", position=1, hero_id=1), step=0)
    repo.add_pick(dsession.id, Pick(team="dire", position=2, hero_id=2), step=1)

    loaded = repo.get_session(dsession.id)
    assert loaded is not None and loaded.current_step == 2
    picks = repo.get_picks(dsession.id)
    assert picks == [
        Pick(team="radiant", position=1, hero_id=1),
        Pick(team="dire", position=2, hero_id=2),
    ]

    repo.finish_session(dsession.id)
    fin = repo.get_session(dsession.id)
    assert fin is not None and fin.picks  # пик-лист остаётся
    assert repo.get_session(999) is None
