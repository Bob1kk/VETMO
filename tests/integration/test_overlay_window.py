"""Интеграционные тесты OverlayWindow (T-011/FR-004, NFR-002).

Review Focus #2: оверлей не крадёт фокус у Dota 2 — проверяем флаги окна
(Frameless | StaysOnTop | Tool), WA_ShowWithoutActivating и NoFocus.

Данные для fill — реальные сервисы (DraftService + OverlayViewModel)
на tmp-SQLite из фикстуры db (conftest.py), сеть не задействована.
"""

import pytest
from PySide6.QtCore import Qt
from sqlalchemy.orm import sessionmaker

from vetmo.data.repositories.hero_repo import HeroRepository
from vetmo.data.repositories.meta_repo import MetaRepository
from vetmo.domain.models import Hero
from vetmo.infra.config import Settings
from vetmo.services.draft_service import DraftService
from vetmo.services.news_service import NewsService
from vetmo.services.settings_service import SettingsService
from vetmo.ui.overlay_window import OverlayWindow
from vetmo.ui.viewmodels.overlay_vm import OverlayViewModel

_HEROES = list(range(100, 110))

_ROLE_FOR_INDEX = {
    0: ["Carry"], 1: ["Midlane"], 2: ["Offlane"],
    3: ["Support"], 4: ["Hard Support"],
}


def _hero(hero_id: int) -> Hero:
    """Герой каталога с ролями под позицию (для position_fit)."""
    return Hero(
        id=hero_id,
        name=f"hero-{hero_id}",
        localized_name=f"Hero {hero_id}",
        primary_attr="str",
        attack_type="Melee",
        roles=_ROLE_FOR_INDEX.get(hero_id % 5, ["Durable"]),
        icon_url=None,
        is_validated=True,
    )


def _make_vm(settings_service, draft_service, sessionmaker) -> OverlayViewModel:
    """OverlayViewModel на реальных сервисах tmp-БД (без сети)."""
    return OverlayViewModel(
        draft_service, settings_service, NewsService(sessionmaker, Settings()),
        hero_lookup=_hero,  # карточкам не нужны запросы к БД героя
    )


EnvT = tuple[SettingsService, DraftService, sessionmaker]
WindowT = tuple[OverlayWindow, SettingsService, DraftService, sessionmaker]


@pytest.fixture()
def overlay_env(db) -> EnvT:
    """Сеансмейкер с каталогом 10 героев + приоритетами позиции 1 и метой."""
    _, smaker = db
    with smaker() as session:
        repo = HeroRepository(session)
        for hero_id in _HEROES:
            repo.upsert(_hero(hero_id))
        patch_id = MetaRepository.ensure_patch(session, "7.39e", None)
        meta = MetaRepository(session)
        meta.upsert(patch_id, 100, 55.0, 12.0)
        meta.upsert(patch_id, 101, 54.0, 11.0)
    settings_service = SettingsService(smaker)
    settings_service.set_position_priorities({1: [100, 101]})
    return settings_service, DraftService(smaker), smaker


@pytest.fixture()
def overlay_window(overlay_env, qtbot) -> WindowT:
    """Окно оверлея, привязанное к реальным сервисам на tmp-БД."""
    settings_service, draft_service, smaker = overlay_env
    window = OverlayWindow(settings_service)
    qtbot.addWidget(window)
    return window, settings_service, draft_service, smaker


def test_overlay_is_always_on_top_and_borderless(overlay_window) -> None:
    """NFR-002 / матрица трассировки: borderless + поверх всех + флаг Tool."""
    window, _, _, _ = overlay_window
    flags = window.windowFlags()
    assert flags & Qt.WindowType.FramelessWindowHint
    assert flags & Qt.WindowType.WindowStaysOnTopHint
    assert flags & Qt.WindowType.Tool


def test_overlay_flags_always_on_top_no_focus_steal(overlay_window) -> None:
    """Review Focus #2: оверлей не активируется и не забирает фокус."""
    window, _, _, _ = overlay_window
    assert window.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    assert window.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    assert window.focusPolicy() == Qt.FocusPolicy.NoFocus
    # повторное применение настроек не возвращает фокус
    window.apply_settings()
    assert window.focusPolicy() == Qt.FocusPolicy.NoFocus


def _entry_names(cards: list) -> list[str]:
    """Имена героев на карточках позиции (whitebox: лейбл name)."""
    return [card._name.text() for card in cards]


def test_fill_shows_cards_for_positions_1_to_5(overlay_window) -> None:
    """FR-004 (матрица): после fill есть карточки рекомендаций позиций 1..5."""
    window, settings_service, draft_service, smaker = overlay_window
    window.apply_snapshot(_make_vm(
        settings_service, draft_service, smaker).compute_all(limit=2))

    # show_dire по умолчанию True -> обе колонки заполнены
    assert not window._radiant.isHidden()
    assert not window._dire.isHidden()

    all_names = {_hero(hero_id).localized_name for hero_id in _HEROES}
    for team in ("_radiant", "_dire"):
        column = getattr(window, team)
        for position in range(1, 6):
            names = _entry_names(column._cards[position])
            assert any(name in all_names for name in names), (
                f"{team} pos {position}: карточки без рекомендаций: {names}")
    # приоритет позиции 1 — первым на карточке позиции 1 (Radiant)
    assert window._radiant._cards[1][0]._name.text() == "Hero 100"


def test_fill_dire_column_respects_show_dire_setting(overlay_window) -> None:
    """Настройка show_dire=False прячет колонку Dire, Radiant остаётся."""
    window, settings_service, draft_service, smaker = overlay_window
    assert settings_service.get_show_dire() is True  # дефолт SettingsService
    settings_service.set_show_dire(False)

    window.apply_snapshot(_make_vm(
        settings_service, draft_service, smaker).compute_all(limit=2))

    assert window._dire.isHidden()
    assert not window._radiant.isHidden()


def test_apply_settings_keeps_visible_overlay(overlay_window) -> None:
    """Смена click-through на видимом оверлее не скрывает окно.

    Регрессия: setWindowFlag пересоздаёт native window и прятал оверлей
    после изменения настроек из лаунчера.
    """
    window, settings_service, _, _ = overlay_window
    flag = Qt.WindowType.WindowTransparentForInput
    settings_service.set_click_through(True)
    window.apply_settings()
    window.show()
    assert window.isVisible()

    settings_service.set_click_through(False)
    window.apply_settings()
    assert window.isVisible()
    assert not bool(window.windowFlags() & flag)

    settings_service.set_click_through(True)
    window.apply_settings()
    assert window.isVisible()
    assert bool(window.windowFlags() & flag)


def test_update_overlay_with_draft_service_does_not_crash(
    overlay_window, qtbot,
) -> None:
    """update_overlay() с реальными сервисами не падает и пингует refresh."""
    window, settings_service, draft_service, smaker = overlay_window
    window.apply_snapshot(_make_vm(
        settings_service, draft_service, smaker).compute_all(limit=2))

    pings: list = []
    window.refresh_requested.connect(lambda: pings.append(1))
    window.update_overlay()
    qtbot.waitSignal(window.refresh_requested, timeout=5000)
    assert pings == [1]
