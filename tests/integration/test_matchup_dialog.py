"""GUI-тесты матчапов: клик по герою и три таблицы диалога."""

from __future__ import annotations

from PySide6.QtCore import Qt

from vetmo.domain.matchup import MatchupEntry, MatchupReport
from vetmo.ui.viewmodels.main_viewmodel import MetaReport, MetaReportRow
from vetmo.ui.widgets.matchup_dialog import MatchupDialog
from vetmo.ui.widgets.meta_report import MetaReportWidget


def _report() -> MetaReport:
    return MetaReport(
        rows=[
            MetaReportRow(
                hero_id=1, name="Anti-Mage", primary_attr="agi",
                attack_type="Melee", win_rate=55.0, pick_rate=12.0,
                ban_rate=20.0, positions=[1],
            ),
        ],
        patch_version="7.41",
    )


def _matchup_report() -> MatchupReport:
    return MatchupReport(
        hero_id=1,
        hero_name="Anti-Mage",
        rank_tier=4,
        bracket="CRUSADER_ARCHON",
        bracket_label="Crusader–Archon",
        period="04.10–10.10.2026",
        counters=[
            MatchupEntry(hero_id=2, name="Axe", win_rate=47.5,
                         match_count=1200, sample_reliable=True),
            MatchupEntry(hero_id=3, name="Bane", win_rate=48.0,
                         match_count=80, sample_reliable=False),
        ],
        good_picks=[
            MatchupEntry(hero_id=4, name="Crystal Maiden", win_rate=58.0,
                         match_count=900, sample_reliable=True),
        ],
        synergies=[
            MatchupEntry(hero_id=5, name="Wraith King", win_rate=57.0,
                         match_count=1500, sample_reliable=True),
        ],
    )


def test_hero_click_opens_matchup_dialog(qtbot, monkeypatch) -> None:
    widget = MetaReportWidget()
    qtbot.addWidget(widget)
    widget.set_meta(_report())
    widget.set_matchup_details_loader(lambda *_: _matchup_report())

    calls: list[dict] = []

    class FakeDialog:
        def __init__(self, **kwargs):
            calls.append(kwargs)

        def show(self) -> None:
            pass

        def raise_(self) -> None:
            pass

        def close(self) -> None:
            pass

        def deleteLater(self) -> None:
            pass

    monkeypatch.setattr(
        "vetmo.ui.widgets.meta_report.MatchupDialog", FakeDialog,
    )
    cell = widget._table.cellWidget(0, 0)
    assert cell is not None
    qtbot.mouseClick(cell, Qt.MouseButton.LeftButton)

    assert len(calls) == 1
    assert calls[0]["hero_id"] == 1
    assert calls[0]["rank_tier"] == 0


def test_matchup_dialog_populates_three_tables(qtbot) -> None:
    dialog = MatchupDialog(
        hero_id=1,
        hero_name="Anti-Mage",
        icon_url=None,
        internal_name="antimage",
        rank_tier=4,
        patch_id=1,
        loader=lambda *_: _matchup_report(),
    )
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.waitUntil(dialog.is_loaded, timeout=3000)

    assert dialog.tab_counts() == (2, 1, 1)
    assert "Crusader–Archon" in dialog._subtitle.text()
    assert "все позиции" in dialog._subtitle.text()
