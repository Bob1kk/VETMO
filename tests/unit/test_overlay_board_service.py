"""Тесты доски оверлея: произвольная запись/очистка клеток (SupabaseDraftService).

Сеть не используется: gateway не сконфигурирован, поэтому сервис работает
на локальном JSON-фолбэке. APPDATA подменяется на tmp-каталог, чтобы не
трогать реальные данные пользователя.
"""

from __future__ import annotations

import pytest

from vetmo.services.supabase_draft import SupabaseDraftService


class _StubGateway:
    """Двойник gateway: не сконфигурирован -> только локальный фолбэк."""

    is_configured = False
    user_id = None


@pytest.fixture()
def service(tmp_path, monkeypatch) -> SupabaseDraftService:
    monkeypatch.setenv("APPDATA", str(tmp_path))
    return SupabaseDraftService(
        _StubGateway(),  # type: ignore[arg-type]
        None,  # type: ignore[arg-type]
        None,  # type: ignore[arg-type]
        None,  # type: ignore[arg-type]
    )


def test_set_pick_allows_arbitrary_cell_order(service) -> None:
    """Пик можно ставить в любую клетку, не соблюдая порядок 2-2-1."""
    state = service.set_pick("dire", 5, 105)
    assert [(p.team, p.position, p.hero_id) for p in state.picks] == [
        ("dire", 5, 105)
    ]
    assert state.current_step == 1

    state = service.set_pick("radiant", 1, 100)
    assert state.current_step == 2
    assert {p.hero_id for p in state.picks} == {100, 105}


def test_set_pick_replaces_hero_in_same_cell(service) -> None:
    """Повторная запись в клетку заменяет героя, не добавляя второй пик."""
    service.set_pick("radiant", 2, 100)
    state = service.set_pick("radiant", 2, 101)
    assert len(state.picks) == 1
    assert state.picks[0].hero_id == 101
    assert state.current_step == 1


def test_set_pick_idempotent_for_same_hero(service) -> None:
    """Повтор той же пары (клетка, герой) не считается ошибкой."""
    service.set_pick("radiant", 3, 100)
    state = service.set_pick("radiant", 3, 100)
    assert len(state.picks) == 1


def test_set_pick_rejects_duplicate_hero(service) -> None:
    """Один герой не может быть в двух клетках."""
    service.set_pick("radiant", 1, 100)
    with pytest.raises(ValueError, match="уже пикнут"):
        service.set_pick("dire", 2, 100)


def test_set_pick_rejects_bad_position(service) -> None:
    """Позиция вне 1..5 — ошибка."""
    with pytest.raises(ValueError, match="Позиция"):
        service.set_pick("radiant", 6, 100)


def test_clear_pick_removes_cell_and_rewinds_step(service) -> None:
    """Очистка клетки убирает пик и уменьшает счётчик шага."""
    service.set_pick("radiant", 1, 100)
    service.set_pick("dire", 1, 101)
    state = service.clear_pick("radiant", 1)
    assert [(p.team, p.hero_id) for p in state.picks] == [("dire", 101)]
    assert state.current_step == 1


def test_clear_pick_on_empty_cell_is_noop(service) -> None:
    """Очистка пустой клетки ничего не меняет."""
    service.set_pick("radiant", 4, 100)
    state = service.clear_pick("dire", 3)
    assert len(state.picks) == 1
