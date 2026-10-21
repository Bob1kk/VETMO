"""Смоук Admin-окна на фейковом контексте (T-103…T-110).

Сеть и Supabase не используются: репозиторий/клиент подменены словарями.
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QLabel  # noqa: E402

from vetmo.admin.window import AdminWindow  # noqa: E402


class FakeSync:
    """Настройки без реальных ключей (значения не должны попасть в UI)."""

    supabase_url = "https://example.supabase.co"
    service_key = "SECRET_SERVICE_KEY"
    stratz_token = "SECRET_STRATZ_TOKEN"
    stratz_api_url = "https://api.stratz.com/graphql"
    secrets_file = Path("secrets.env")


class FakeRepository:
    """Минимальные SELECT-ответы для вкладок."""

    def latest_patch(self) -> dict[str, Any]:
        return {
            "id": 12,
            "version": "7.40",
            "release_date": "2026-10-01",
            "is_current": True,
        }

    def last_run(self) -> dict[str, Any]:
        return {
            "id": 7,
            "status": "ok",
            "started_at": "2026-10-21T10:00:00+00:00",
            "finished_at": "2026-10-21T10:01:00+00:00",
            "trigger_source": "admin-app",
            "request_id": "req-7",
            "patch_version": "7.40",
            "rows_meta": 127,
            "rows_matchups": 500,
            "details": {"period_end": "2026-10-20", "slices": 3, "errors": []},
            "error": None,
        }

    def list_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        return [self.last_run()][: max(0, limit)]

    def heroes(self) -> list[dict[str, Any]]:
        return [
            {"id": 1, "name": "antimage", "localized_name": "Anti-Mage"},
            {"id": 2, "name": "axe", "localized_name": "Axe"},
        ]

    def meta_rows(
        self,
        rank_tier: int | None = None,
        position: int | None = None,
        search: str | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        rows = [
            {
                "hero_id": 1,
                "hero_name": "Anti-Mage",
                "win_rate": 53.2,
                "pick_rate": 12.1,
                "ban_rate": 8.4,
                "match_count": 12000,
                "delta_win": 1.2,
                "delta_pick": -0.4,
            },
            {
                "hero_id": 2,
                "hero_name": "Axe",
                "win_rate": 47.8,
                "pick_rate": 9.3,
                "ban_rate": None,
                "match_count": 9000,
                "delta_win": -0.8,
                "delta_pick": 0.3,
            },
        ]
        query = (search or "").casefold()
        return [row for row in rows if not query or query in row["hero_name"].casefold()]

    def matchups(self, hero_id: int, patch_id: int | None = None) -> list[dict[str, Any]]:
        return [
            {
                "patch_id": 12,
                "hero_id": hero_id,
                "vs_hero_id": 2,
                "kind": "vs",
                "rank_bracket": "ALL",
                "bucket": "counter",
                "bucket_rank": 1,
                "win_rate": 45.0,
                "match_count": 100,
                "sample_reliable": False,
            },
            {
                "patch_id": 12,
                "hero_id": hero_id,
                "vs_hero_id": 2,
                "kind": "vs",
                "rank_bracket": "ALL",
                "bucket": "good",
                "bucket_rank": 1,
                "win_rate": 55.0,
                "match_count": 900,
                "sample_reliable": True,
            },
            {
                "patch_id": 12,
                "hero_id": hero_id,
                "vs_hero_id": 2,
                "kind": "with",
                "rank_bracket": "ALL",
                "bucket": "synergy",
                "bucket_rank": 1,
                "win_rate": 54.0,
                "match_count": 900,
                "sample_reliable": True,
            },
        ]


class FakeClient:
    """STRATZ-клиент без сети."""

    def execute(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        return {"constants": {"gameVersions": [{"id": 1, "name": "7.40"}]}}

    def game_versions(self) -> list[dict[str, Any]]:
        return [{"id": 1, "name": "7.40"}]

    def close(self) -> None:
        pass


def _context() -> SimpleNamespace:
    return SimpleNamespace(
        sync=FakeSync(),
        client=FakeClient(),
        repository=FakeRepository(),
        secrets_path=Path("C:/Users/test/AppData/Roaming/VETMO/secrets.env"),
        close=lambda: None,
    )


def test_admin_window_builds_and_switches_tabs(qtbot) -> None:
    window = AdminWindow(_context())
    qtbot.addWidget(window)
    window.show()

    assert window.tab_titles() == [
        "Обзор",
        "Синхронизация",
        "Мета",
        "Матчапы",
        "Сырые данные",
        "История",
        "Настройки",
    ]
    for index in range(7):
        window.select_tab(index)
        assert window.current_tab_index() == index
    qtbot.wait(250)


def test_admin_window_does_not_render_secret_values(qtbot) -> None:
    window = AdminWindow(_context())
    qtbot.addWidget(window)
    window.show()
    qtbot.wait(100)

    texts = " ".join(label.text() for label in window.findChildren(QLabel))
    assert "SECRET_SERVICE_KEY" not in texts
    assert "SECRET_STRATZ_TOKEN" not in texts
    assert "service_role:" in texts
    assert "STRATZ token:" in texts
    assert "задан" in texts


def test_meta_table_loads_rows_in_background(qtbot) -> None:
    from vetmo.admin.tabs.meta_tab import MetaTab

    window = AdminWindow(_context())
    qtbot.addWidget(window)
    tab = window.findChild(MetaTab)
    assert tab is not None
    qtbot.waitUntil(lambda: tab.row_count() == 2, timeout=3000)
    assert "Загружено героев: 2" in tab.state_text()


def test_matchups_catalog_and_buckets(qtbot) -> None:
    from vetmo.admin.tabs.matchups_tab import MatchupsTab

    window = AdminWindow(_context())
    qtbot.addWidget(window)
    tab = window.findChild(MatchupsTab)
    assert tab is not None
    qtbot.waitUntil(lambda: tab.hero_options() == 2, timeout=3000)
    qtbot.waitUntil(lambda: "строк: 3" in tab.state_text(), timeout=3000)


def test_runs_history_loads_and_shows_details(qtbot) -> None:
    from vetmo.admin.tabs.runs_tab import RunsTab

    window = AdminWindow(_context())
    qtbot.addWidget(window)
    tab = window.findChild(RunsTab)
    assert tab is not None
    qtbot.waitUntil(lambda: tab.row_count() == 1, timeout=3000)
    qtbot.wait(100)
    assert "req-7" in tab._details.toPlainText()


def test_raw_query_executes_in_background(qtbot) -> None:
    from vetmo.admin.tabs.raw_tab import RawTab

    window = AdminWindow(_context())
    qtbot.addWidget(window)
    tab = window.findChild(RawTab)
    assert tab is not None
    tab._execute()
    qtbot.waitUntil(lambda: "gameVersions" in tab.viewer_text(), timeout=3000)


def test_settings_connection_checks(qtbot) -> None:
    from vetmo.admin.tabs.settings_tab import SettingsTab

    window = AdminWindow(_context())
    qtbot.addWidget(window)
    tab = window.findChild(SettingsTab)
    assert tab is not None

    tab._check_supabase()
    qtbot.waitUntil(
        lambda: "Supabase: подключение работает" in tab.result_text(),
        timeout=3000,
    )
    tab._check_stratz()
    qtbot.waitUntil(
        lambda: "STRATZ: подключение работает" in tab.result_text(),
        timeout=3000,
    )
