"""Регрессии панели меты: ранги 1..8, поиск, сортировка и сводка."""

from vetmo.ui.viewmodels.main_viewmodel import MetaReport, MetaReportRow
from vetmo.ui.widgets.meta_report import MetaReportWidget


def _report() -> MetaReport:
    return MetaReport(
        rows=[
            MetaReportRow(
                hero_id=1, name="Anti-Mage", primary_attr="agi",
                attack_type="Melee", win_rate=55.0, pick_rate=12.0,
                ban_rate=20.0, positions=[1],
            ),
            MetaReportRow(
                hero_id=2, name="Axe", primary_attr="str",
                attack_type="Melee", win_rate=51.0, pick_rate=8.0,
                ban_rate=None, positions=[3],
            ),
        ],
        patch_version="7.41",
    )


def test_rank_combo_covers_all_tiers(qtbot) -> None:
    """Divine=7 и Immortal=8 присутствуют (раньше Immortal был 7)."""
    widget = MetaReportWidget()
    qtbot.addWidget(widget)

    values = {
        widget._rank.itemData(index)
        for index in range(widget._rank.count())
    }
    labels = {
        widget._rank.itemText(index)
        for index in range(widget._rank.count())
    }
    assert values == {-1, 1, 2, 3, 4, 5, 6, 7, 8}
    assert {"Divine", "Immortal"} <= labels
    assert widget.filters() == (None, None)


def test_rank_filter_returns_selected_tier(qtbot) -> None:
    """Фильтр ранга уходит в серверный запрос как 1..8, «Все» — None."""
    widget = MetaReportWidget()
    qtbot.addWidget(widget)

    widget._rank.setCurrentIndex(widget._rank.findData(8))
    assert widget.filters() == (None, 8)
    widget._position.setCurrentIndex(widget._position.findData(4))
    assert widget.filters() == (4, 8)

    widget._reset_button.click()
    assert widget.filters() == (None, None)


def test_search_and_stats_use_loaded_rows(qtbot) -> None:
    """Все строки попадают в таблицу; поиск сужает выборку и статистику."""
    widget = MetaReportWidget()
    qtbot.addWidget(widget)
    widget.set_meta(_report())

    assert widget.row_count() == 2
    assert widget._patch_label.text() == "ПАТЧ 7.41"
    assert widget._stat_heroes._value_label.text() == "2"
    assert widget._stat_leader._value_label.text() == "Anti-Mage"

    widget._search.setText("axe")
    assert widget.row_count() == 1
    assert widget._stat_wr._value_label.text() == "51,00%"
    assert widget._stat_leader._value_label.text() == "Axe"


def test_sort_by_name_and_ban(qtbot) -> None:
    """Сортировка не теряет строки: имя A–Z и pro-баны ↓."""
    widget = MetaReportWidget()
    qtbot.addWidget(widget)
    widget.set_meta(_report())

    widget._sort.setCurrentIndex(widget._sort.findData("name"))
    assert [row.name for row in widget._view_rows] == ["Anti-Mage", "Axe"]

    widget._sort.setCurrentIndex(widget._sort.findData("ban"))
    assert [row.name for row in widget._view_rows] == ["Anti-Mage", "Axe"]
