"""Тесты диалога выбора героя для клеток оверлея (фильтр по атрибутам)."""

from __future__ import annotations

from PySide6.QtCore import Qt

from vetmo.domain.models import Hero
from vetmo.ui.widgets.hero_pick_dialog import HeroPickDialog


def _hero(hero_id: int, name: str, attr: str) -> Hero:
    return Hero(
        id=hero_id, name=f"npc_dota_hero_{hero_id}", localized_name=name,
        primary_attr=attr, attack_type="Melee", roles=["Carry"],
        icon_url=None, is_validated=True,
    )


_HEROES = [
    _hero(1, "Axe", "str"),
    _hero(2, "Anti-Mage", "agi"),
    _hero(3, "Crystal Maiden", "int"),
    _hero(4, "Io", "all"),
]


def test_attribute_filter_limits_hero_list(qtbot) -> None:
    """Фильтр «Сила/Ловкость/Интеллект/Универсал» сужает список героев."""
    dialog = HeroPickDialog(_HEROES, "radiant", 3)
    qtbot.addWidget(dialog)

    assert sorted(dialog.visible_hero_ids()) == [1, 2, 3, 4]

    dialog.set_attribute_filter("str")
    assert dialog.visible_hero_ids() == [1]

    dialog.set_attribute_filter("int")
    assert dialog.visible_hero_ids() == [3]

    dialog.set_attribute_filter("all")
    assert dialog.visible_hero_ids() == [4]


def test_search_filters_and_submit_emits_hero(qtbot) -> None:
    """Поиск по имени + подтверждение отдают id выбранного героя."""
    dialog = HeroPickDialog(_HEROES, "dire", 1)
    qtbot.addWidget(dialog)

    dialog._search.setText("anti")
    assert dialog.visible_hero_ids() == [2]

    with qtbot.waitSignal(dialog.hero_selected, timeout=3000) as blocker:
        dialog._submit()
    assert blocker.args == [2]


def test_current_hero_is_preselected(qtbot) -> None:
    """В диалоге заранее выделен герой, который уже стоит в клетке."""
    dialog = HeroPickDialog(_HEROES, "radiant", 4, current_hero_id=3)
    qtbot.addWidget(dialog)

    item = dialog._list.currentItem()
    assert item is not None
    assert int(item.data(Qt.ItemDataRole.UserRole)) == 3
