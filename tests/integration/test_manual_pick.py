"""Интеграционные тесты ручного ввода пиков (T-013 / FR-008).

ManualPickDialog полностью автономен (каталог героев передаётся списком,
как делает MainWindow._manual_dialog_ready), поэтому сеть не трогаем;
DraftService работает на tmp-SQLite из фикстуры db (conftest.py).
"""

import pytest

from vetmo.data.repositories.hero_repo import HeroRepository
from vetmo.domain.models import DraftSession, Hero
from vetmo.services.draft_service import DraftService
from vetmo.ui.widgets.manual_pick_dialog import ManualPickDialog


def _hero(hero_id: int, name: str) -> Hero:
    """Каталожный герой для диалога (icon_url=None -> без сети)."""
    return Hero(
        id=hero_id, name=name.lower(), localized_name=name,
        primary_attr="str", attack_type="Melee",
        roles=["Carry"], icon_url=None, is_validated=True,
    )


@pytest.fixture()
def heroes() -> list[Hero]:
    """Мини-каталог: 3 героя (id 100..102), как после синхронизации."""
    return [
        _hero(100, "Apx Hero"),
        _hero(101, "Nyx Assassin"),
        _hero(102, "Rubick"),
    ]


@pytest.fixture()
def dialog(heroes) -> ManualPickDialog:
    """Свежий диалог ручного ввода."""
    return ManualPickDialog(heroes, None)


def test_manual_pick_updates_draft_session(heroes, db) -> None:
    """FR-008 (матрица): пик из диалога через DraftService.add_pick_auto
    записывает пик — шаг драфта 0 -> 1, команда/позиция по правилам 2-2-1.
    """
    _, sessionmaker = db
    with sessionmaker() as session:
        for hero in heroes:
            HeroRepository(session).upsert(hero)

    draft = DraftService(sessionmaker)
    draft.start_session()

    # как MainWindow._manual_dialog_ready: каталог берётся из БД
    with sessionmaker() as session:
        catalog = HeroRepository(session).get_all()
    dialog = ManualPickDialog(catalog, None)
    received: list[tuple[object, int]] = []
    states: list[DraftSession] = []

    def on_pick(position: object, hero_id: int) -> None:
        """Коллбек, эквивалентный MainWindow._on_pick_requested."""
        received.append((position, hero_id))
        states.append(draft.add_pick_auto(position, hero_id))

    dialog.pick_requested.connect(on_pick)

    row = next(i for i in range(dialog._list.count())
               if "Apx" in dialog._list.item(i).text())
    dialog._list.setCurrentRow(row)
    dialog._submit()

    assert received == [(None, 100)]  # позиция «авто» -> None
    state = states[-1]
    assert state is not None and state.current_step == 1
    assert state.picks[0].hero_id == 100
    assert state.picks[0].team == "radiant"  # шаг 0 по 2-2-1 пикает Radiant
    assert state.picks[0].position == 1  # свободная позиция по порядку


def test_manual_pick_dialog_signal_carries_position(heroes) -> None:
    """Выбранная позиция комбобокса попадает в сигна pick_requested."""
    dialog = ManualPickDialog(heroes, None)
    received: list[tuple[object, int]] = []
    dialog.pick_requested.connect(lambda pos, hid: received.append((pos, hid)))

    dialog._position.setCurrentIndex(3)  # itemData == 3 («Позиция: 3»)
    dialog._list.setCurrentRow(2)  # Rubick
    dialog._submit()

    assert received == [(3, 102)]


def test_manual_pick_search_filters_hero_list(heroes) -> None:
    """Поиск фильтрует список героев по localized_name."""
    dialog = ManualPickDialog(heroes, None)
    assert dialog._list.count() == 3

    dialog._search.setText("nyx")
    assert dialog._list.count() == 1
    assert "Nyx" in dialog._list.item(0).text()


def test_manual_pick_submit_without_selection_is_rejected(
    heroes, monkeypatch,
) -> None:
    """Подтверждение без выбранного героя не эмвит сигнал и не роняет диалог."""
    dialog = ManualPickDialog(heroes, None)
    received: list[tuple[object, int]] = []
    dialog.pick_requested.connect(lambda pos, hid: received.append((pos, hid)))
    warnings: list[tuple] = []

    monkeypatch.setattr(
        "vetmo.ui.widgets.manual_pick_dialog.QMessageBox.information",
        lambda *args, **kwargs: warnings.append(tuple(args)),
    )
    dialog._submit()
    assert received == []
    assert warnings, "ожидали диалог-подсказку «Нет выбора»"


def test_manual_pick_show_state_marks_step_and_finish(heroes) -> None:
    """show_state показывает текущий шаг и завершённый драфт."""
    dialog = ManualPickDialog(heroes, None)

    dialog.show_state(DraftSession(id=1, current_step=0, total_picks=10))
    assert "Шаг 1/10" in dialog._state_label.text()
    assert dialog._submit_button.isEnabled()

    dialog.show_state(DraftSession(id=1, current_step=10, total_picks=10))
    assert "Драфт завершён" in dialog._state_label.text()
    assert not dialog._submit_button.isEnabled()
