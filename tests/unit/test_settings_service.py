"""Тесты SettingsService (T-009): оверлей, темы, приоритеты позиций."""

import pytest

from vetmo.data.repositories.settings_repo import SettingsRepository
from vetmo.services.settings_service import SettingsService


@pytest.fixture()
def svc(db) -> SettingsService:
    """Сервис от общего sessionmaker, персистится между вызовами."""
    _, sessionmaker = db
    return SettingsService(sessionmaker)


def test_overlay_defaults(svc: SettingsService) -> None:
    """Дефолты: (20,20), opacity 0.85, dark, click-through False, Dire True.

    Click-through выключен, чтобы шестерёнка оверлея принимала мышь; это
    явная опция для клавиатурного управления.
    """
    assert svc.get_overlay_position() == (20, 20)
    assert svc.get_opacity() == 0.85
    assert svc.get_theme() == "dark"
    assert svc.get_click_through() is False
    assert svc.get_show_dire() is True


def test_persist_position_and_opacity(svc: SettingsService) -> None:
    """Позиция и прозрачность сохраняются между экземплярами сервиса."""
    svc.set_overlay_position(200, 150)
    svc.set_opacity(0.4)
    s2 = SettingsService(svc._sessionmaker)  # noqa: SLF001 — тест персистентности
    assert s2.get_overlay_position() == (200, 150)
    assert s2.get_opacity() == 0.4


def test_opacity_clamped(svc: SettingsService) -> None:
    """set_opacity клампит в 0.0..1.0."""
    svc.set_opacity(5.0)
    assert svc.get_opacity() == 1.0
    svc.set_opacity(-3.0)
    assert svc.get_opacity() == 0.0


def test_theme_persist_and_validate(svc: SettingsService) -> None:
    """Тема сохраняется; недопустимая -> ValueError."""
    svc.set_theme("light")
    assert svc.get_theme() == "light"
    with pytest.raises(ValueError, match="theme"):
        svc.set_theme("neon")
    assert svc.get_theme() == "light"


def test_flags_persist(svc: SettingsService) -> None:
    """Click-through и show_dire переключаются."""
    svc.set_click_through(True)
    svc.set_show_dire(False)
    assert svc.get_click_through() is True
    assert svc.get_show_dire() is False
    svc.set_click_through(False)
    assert svc.get_click_through() is False


def test_position_priorities_roundtrip(svc: SettingsService) -> None:
    """Приоритеты позиций сохраняются как JSON: 1..5 -> список hero_id."""
    svc.set_position_priorities({1: [1, 2], 3: [7], 5: [3]})
    s2 = SettingsService(svc._sessionmaker)  # noqa: SLF001
    assert s2.get_position_priorities() == {1: [1, 2], 3: [7], 5: [3]}


def test_position_priorities_sanitized(svc: SettingsService) -> None:
    """Невалидные позиции (>5) и hero_id (<1) отбрасываются."""
    svc.set_position_priorities({6: [1], 0: [1], 2: [-5, 4], 1: []})
    assert svc.get_position_priorities() == {2: [4], 1: []}


def test_empty_priorities_default(svc: SettingsService) -> None:
    """Без данных — пустой словарь, не падает."""
    assert svc.get_position_priorities() == {}


def test_malformed_priorities_are_skipped(svc: SettingsService) -> None:
    """Битые позиции/hero_id не роняют чтение настроек."""
    with svc._sessionmaker() as session:  # noqa: SLF001 — тест хранилища
        SettingsRepository(session).set(
            "position_priorities",
            '{"1": ["x", 2], "bad": [1], "2": null, "3": [3], "9": [4]}',
        )
    assert svc.get_position_priorities() == {1: [2], 3: [3]}
