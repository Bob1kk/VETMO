"""Регрессии панели меты: чипсы рангов соответствуют тирам OpenDota 1..8."""

from vetmo.ui.widgets.meta_report import MetaReportWidget


def test_rank_chips_cover_all_tiers(qtbot) -> None:
    """Divine=7 и Immortal=8 присутствуют (раньше Immortal был 7)."""
    widget = MetaReportWidget()
    qtbot.addWidget(widget)

    buttons = widget._rank_group.buttons()
    values = {button.property("filterValue") for button in buttons}
    labels = {button.text() for button in buttons}
    assert values == {None, 1, 2, 3, 4, 5, 6, 7, 8}
    assert {"Divine", "Immortal"} <= labels
