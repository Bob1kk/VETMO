"""Тесты HeroRepository и схемы БД (T-004): idempotent upsert обязателен."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from vetmo.data.db import create_db, migrate
from vetmo.data.repositories.hero_repo import HeroRepository
from vetmo.domain.models import Hero


def _hero(id_: int, name: str) -> Hero:
    return Hero(
        id=id_, name=name, localized_name=name.title(),
        primary_attr="agi", attack_type="Melee", roles=["Carry"],
        icon_url=None, is_validated=True,
    )


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


def test_hero_upsert_insert_and_get(session: Session) -> None:
    """Insert -> get_by_id/get_all возвращают доменную модель."""
    repo = HeroRepository(session)
    repo.upsert(_hero(1, "anti-mage"))
    hero = repo.get_by_id(1)
    assert hero is not None
    assert hero.name == "anti-mage"
    assert hero.roles == ["Carry"] and hero.is_validated is True
    assert len(repo.get_all()) == 1


def test_hero_upsert_is_idempotent_no_duplicates(session: Session) -> None:
    """Повторный upsert того же name не создаёт дублей (Review Focus #3)."""
    repo = HeroRepository(session)
    repo.upsert(_hero(1, "anti-mage"))
    repo.upsert(_hero(2, "anti-mage"))  # тот же name, другой id
    heroes = repo.get_all()
    assert len(heroes) == 1
    assert heroes[0].name == "anti-mage"


def test_hero_upsert_updates_fields_on_conflict(session: Session) -> None:
    """ON CONFLICT(name) DO UPDATE: поля перезаписываются."""
    repo = HeroRepository(session)
    repo.upsert(_hero(1, "anti-mage"))
    repo.upsert(Hero(id=1, name="anti-mage", localized_name="AM",
                     primary_attr="agi", attack_type="Melee",
                     roles=["Carry", "Blink"], icon_url="http://x/y.png",
                     is_validated=False))
    hero = repo.get_by_id(1)
    assert hero is not None
    assert hero.localized_name == "AM"
    assert hero.roles == ["Carry", "Blink"]
    assert hero.is_validated is False
    assert len(repo.get_all()) == 1


def test_hero_get_by_id_missing_returns_none(session: Session) -> None:
    """Отсутствующий герой -> None."""
    assert HeroRepository(session).get_by_id(999) is None
