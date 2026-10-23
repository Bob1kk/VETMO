"""Тесты ``AdminRepository`` (T-112): фильтры, поиск и join имён героев.

Сеть не используется: ``SupabaseGateway`` подменяется фейком с заранее
заданными ответами. SQL/PostgREST-обёртка проверяется отдельно в unit-тестах.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from vetmo.admin.repository import META_WINDOW_DAYS, AdminRepository

Row = dict[str, Any]


class FakeGateway:
    """Минимальный двойник ``SupabaseGateway``: отдаёт строки по имени таблицы."""

    def __init__(self, tables: dict[str, list[Row]] | None = None) -> None:
        self._tables = tables or {}
        self.calls: list[dict[str, Any]] = []

    def select(
        self,
        table: str,
        *,
        columns: str = "*",
        filters: dict[str, Any] | None = None,
        order: tuple[str, bool] | None = None,
        limit: int | None = None,
    ) -> list[Row]:
        self.calls.append(
            {
                "table": table,
                "columns": columns,
                "filters": filters,
                "order": order,
                "limit": limit,
            }
        )
        return deepcopy(self._tables.get(table, []))

    def calls_for(self, table: str) -> list[dict[str, Any]]:
        return [call for call in self.calls if call["table"] == table]


def _repo(tables: dict[str, list[Row]] | None = None) -> tuple[AdminRepository, FakeGateway]:
    gateway = FakeGateway(tables)
    return AdminRepository(gateway), gateway  # type: ignore[arg-type]


# ------------------------------------------------------------------ патчи --
def test_latest_patch_returns_first_row() -> None:
    repo, gateway = _repo(
        {"vetmo_patches": [{"id": 12, "version": "7.41", "is_current": True}]}
    )

    assert repo.latest_patch() == {"id": 12, "version": "7.41", "is_current": True}
    call = gateway.calls_for("vetmo_patches")[0]
    assert call["columns"] == "id,version,release_date,is_current"
    assert call["order"] == ("id", True)
    assert call["limit"] == 1


def test_latest_patch_returns_none_for_empty_table() -> None:
    repo, _ = _repo()

    assert repo.latest_patch() is None


# --------------------------------------------------------------- запуски --
def test_list_runs_returns_empty_for_non_positive_limit() -> None:
    repo, gateway = _repo({"vetmo_sync_runs": [{"id": 1}]})

    assert repo.list_runs(0) == []
    assert repo.list_runs(-5) == []
    assert gateway.calls == []


def test_list_runs_orders_newest_first() -> None:
    rows = [{"id": 2}, {"id": 1}]
    repo, gateway = _repo({"vetmo_sync_runs": rows})

    assert repo.list_runs(limit=7) == rows
    call = gateway.calls_for("vetmo_sync_runs")[0]
    assert call["order"] == ("id", True)
    assert call["limit"] == 7


def test_last_run_returns_none_for_empty_table() -> None:
    repo, _ = _repo()

    assert repo.last_run() is None


# ------------------------------------------------------------------ мета --
def test_meta_rows_requires_a_patch() -> None:
    repo, gateway = _repo({"vetmo_meta": [{"hero_id": 1}]})

    assert repo.meta_rows() == []
    assert gateway.calls_for("vetmo_meta") == []


def test_meta_rows_passes_filters_and_enriches_hero_names() -> None:
    repo, gateway = _repo(
        {
            "vetmo_patches": [{"id": "5"}],
            "vetmo_heroes": [
                {"id": 1, "name": "antimage", "localized_name": "Anti-Mage"},
                {"id": 2, "name": "axe", "localized_name": "Axe"},
            ],
            "vetmo_meta": [
                {"hero_id": 2, "win_rate": 47.8},
                {"hero_id": 1, "win_rate": 53.2},
            ],
        }
    )

    rows = repo.meta_rows(rank_tier=3, position=2, limit=10)

    assert [row["hero_name"] for row in rows] == ["Axe", "Anti-Mage"]
    assert [row["hero_internal_name"] for row in rows] == ["axe", "antimage"]
    call = gateway.calls_for("vetmo_meta")[0]
    assert call["filters"] == {
        "patch_id": 5,
        "window_days": META_WINDOW_DAYS,
        "rank_tier": 3,
        "position": 2,
    }
    assert call["order"] == ("win_rate", True)
    # Ограничение применяется в Python после фильтрации по имени.
    assert call["limit"] is None


def test_meta_rows_search_matches_localized_and_internal_names_case_insensitive() -> None:
    repo, _ = _repo(
        {
            "vetmo_patches": [{"id": 1}],
            "vetmo_heroes": [
                {"id": 1, "name": "antimage", "localized_name": "Anti-Mage"},
                {"id": 2, "name": "axe", "localized_name": "Axe"},
            ],
            "vetmo_meta": [
                {"hero_id": 1, "win_rate": 53.2},
                {"hero_id": 2, "win_rate": 47.8},
            ],
        }
    )

    assert [row["hero_id"] for row in repo.meta_rows(search="AXE")] == [2]
    assert [row["hero_id"] for row in repo.meta_rows(search="  anti  ")] == [1]
    assert [row["hero_id"] for row in repo.meta_rows(search="")] == [1, 2]
    assert [row["hero_id"] for row in repo.meta_rows(search="нет такого")] == []


def test_meta_rows_respects_limit_after_search() -> None:
    repo, _ = _repo(
        {
            "vetmo_patches": [{"id": 1}],
            "vetmo_heroes": [
                {"id": 1, "name": "antimage", "localized_name": "Anti-Mage"},
                {"id": 2, "name": "axe", "localized_name": "Axe"},
            ],
            "vetmo_meta": [
                {"hero_id": 1, "win_rate": 53.2},
                {"hero_id": 2, "win_rate": 47.8},
            ],
        }
    )

    rows = repo.meta_rows(search="a", limit=1)

    assert len(rows) == 1
    assert rows[0]["hero_id"] == 1


def test_meta_rows_falls_back_to_hero_id_when_catalog_is_missing() -> None:
    repo, _ = _repo(
        {
            "vetmo_patches": [{"id": 1}],
            "vetmo_meta": [{"hero_id": 99, "win_rate": 50.0}],
        }
    )

    row = repo.meta_rows()[0]

    assert row["hero_name"] == "hero_99"
    assert row["hero_internal_name"] == ""


def test_meta_rows_zero_limit_returns_empty_without_queries() -> None:
    repo, gateway = _repo({"vetmo_patches": [{"id": 1}], "vetmo_meta": [{"hero_id": 1}]})

    assert repo.meta_rows(limit=0) == []
    assert gateway.calls == []


# --------------------------------------------------------------- матчапы --
def test_matchups_uses_explicit_patch_without_latest_lookup() -> None:
    rows = [{"hero_id": 12, "vs_hero_id": 3, "win_rate": 44.0}]
    repo, gateway = _repo({"vetmo_hero_matchups": rows})

    assert repo.matchups(hero_id=12, patch_id=7) == rows
    assert gateway.calls_for("vetmo_patches") == []
    call = gateway.calls_for("vetmo_hero_matchups")[0]
    assert call["filters"] == {"patch_id": 7, "hero_id": 12}
    assert call["order"] == ("win_rate", True)
    assert call["limit"] == 5000


def test_matchups_resolves_latest_patch_when_patch_id_is_missing() -> None:
    repo, gateway = _repo(
        {
            "vetmo_patches": [{"id": "12"}],
            "vetmo_hero_matchups": [{"hero_id": 1}],
        }
    )

    assert repo.matchups(hero_id=1) == [{"hero_id": 1}]
    call = gateway.calls_for("vetmo_hero_matchups")[0]
    assert call["filters"] == {"patch_id": 12, "hero_id": 1}


def test_matchups_returns_empty_without_any_patch() -> None:
    repo, gateway = _repo({"vetmo_hero_matchups": [{"hero_id": 1}]})

    assert repo.matchups(hero_id=1) == []
    assert gateway.calls_for("vetmo_hero_matchups") == []


# ------------------------------------------------------------------ баны --
def test_ban_stats_without_rank_has_no_filters() -> None:
    rows = [{"hero_id": 1, "snapshot_date": "2026-10-20"}]
    repo, gateway = _repo({"vetmo_ban_stats": rows})

    assert repo.ban_stats(limit=3) == rows
    call = gateway.calls_for("vetmo_ban_stats")[0]
    assert call["filters"] is None
    assert call["order"] == ("snapshot_date", True)
    assert call["limit"] == 3


def test_ban_stats_filters_by_rank() -> None:
    repo, gateway = _repo({"vetmo_ban_stats": []})

    assert repo.ban_stats(rank_tier=4) == []
    call = gateway.calls_for("vetmo_ban_stats")[0]
    assert call["filters"] == {"rank_tier": 4}


def test_ban_stats_non_positive_limit_returns_empty() -> None:
    repo, gateway = _repo({"vetmo_ban_stats": [{"hero_id": 1}]})

    assert repo.ban_stats(limit=0) == []
    assert gateway.calls == []


# ------------------------------------------------------------- служебное --
def test_gateway_property_exposes_the_backing_gateway() -> None:
    gateway = FakeGateway()
    repo = AdminRepository(gateway)  # type: ignore[arg-type]

    assert repo.gateway is gateway
