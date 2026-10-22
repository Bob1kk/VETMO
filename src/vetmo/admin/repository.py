"""Репозиторий Admin-приложения: чтение reference-данных через service_role.

Admin — единственная программа с ``service_role``; UI только читает, а
запись выполняет ``sync_all``. Ключи здесь не логируются и не покидают
``AdminContext``.
"""

from __future__ import annotations

from typing import Any

from vetmo.infra.supabase_gateway import SupabaseGateway

Row = dict[str, Any]

# Окно меты, которое пишет sync (см. supabase/migrations/20261020_001_init.sql).
META_WINDOW_DAYS = 7


def _as_int(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[call-overload]
    except (TypeError, ValueError):
        return None


class AdminRepository:
    """Тонкие SELECT-запросы к таблицам ``vetmo_*`` для Admin-окна."""

    def __init__(self, gateway: SupabaseGateway) -> None:
        self._gateway = gateway

    @property
    def gateway(self) -> SupabaseGateway:
        """Gateway с service_role, если UI нужен прямой доступ."""
        return self._gateway

    # ------------------------------------------------------------- патчи --
    def latest_patch(self) -> Row | None:
        """Текущий патч (``is_current``) или самый свежий по ``id``."""
        rows = self._gateway.select(
            "vetmo_patches",
            columns="id,version,release_date,is_current",
            order=("id", True),
            limit=1,
        )
        current = [r for r in rows if r.get("is_current")]
        if current:
            return current[0]  # order=id desc -> самый свежий текущий
        return rows[0] if rows else None

    # ------------------------------------------------------------ запуски --
    def last_run(self) -> Row | None:
        """Последний запуск ``vetmo_sync_runs`` или ``None``."""
        rows = self._gateway.select(
            "vetmo_sync_runs",
            order=("id", True),
            limit=1,
        )
        return rows[0] if rows else None

    def list_runs(self, limit: int = 50) -> list[Row]:
        """История запусков, свежие сверху."""
        if limit <= 0:
            return []
        return self._gateway.select(
            "vetmo_sync_runs",
            order=("id", True),
            limit=int(limit),
        )

    # -------------------------------------------------------------- герои --
    def heroes(self) -> list[Row]:
        """Справочник героев: ``id``, внутреннее и отображаемое имя."""
        return self._gateway.select(
            "vetmo_heroes",
            columns="id,name,localized_name",
            order=("localized_name", False),
        )

    # ---------------------------------------------------------------- мета --
    def meta_rows(
        self,
        rank_tier: int | None = None,
        position: int | None = None,
        search: str | None = None,
        limit: int = 500,
    ) -> list[Row]:
        """Строки ``vetmo_meta`` последнего патча (``window_days=7``).

        Источник — OpenDota (``source='opendota'``): ранги 0..7, позиция 0
        (все позиции). STRATZ-строки (позиции 1..5) не попадают в отчёт.
        ``search`` фильтрует по имени героя уже в Python: PostgREST-обёртка
        не поддерживает ``ilike``. В строки добавляются ``hero_name`` и
        ``hero_internal_name`` из ``vetmo_heroes``.
        """
        if limit <= 0:
            return []
        patch = self.latest_patch()
        patch_id = _as_int((patch or {}).get("id"))
        if patch_id is None:
            return []

        # Ранг 0 = все ранги (дефолт), позиция 0 = все позиции.
        filters: dict[str, Any] = {
            "patch_id": patch_id,
            "window_days": META_WINDOW_DAYS,
            "position": position if position is not None else 0,
        }
        filters["rank_tier"] = int(rank_tier) if rank_tier is not None else 0

        rows = self._gateway.select(
            "vetmo_meta",
            filters=filters,
            order=("win_rate", True),
        )

        by_id: dict[int, Row] = {}
        for hero in self.heroes():
            hero_id = _as_int(hero.get("id"))
            if hero_id is not None:
                by_id[hero_id] = hero

        query = (search or "").strip().casefold()
        result: list[Row] = []
        for row in rows:
            hero_id = _as_int(row.get("hero_id"))
            hero = by_id.get(hero_id, {}) if hero_id is not None else {}
            display = str(hero.get("localized_name") or hero.get("name") or "")
            internal = str(hero.get("name") or "")
            if query and query not in display.casefold() and query not in internal.casefold():
                continue
            enriched = dict(row)
            enriched["hero_name"] = display or f"hero_{hero_id}"
            enriched["hero_internal_name"] = internal
            result.append(enriched)
            if len(result) >= int(limit):
                break
        return result

    # ------------------------------------------------------------ матчапы --
    def matchups(self, hero_id: int, patch_id: int | None = None) -> list[Row]:
        """Все матчапы героя (``vs`` и ``with``, все брекеты) для патча."""
        resolved = self._resolve_patch_id(patch_id)
        if resolved is None:
            return []
        return self._gateway.select(
            "vetmo_hero_matchups",
            filters={"patch_id": resolved, "hero_id": int(hero_id)},
            order=("win_rate", True),
            limit=5000,
        )

    # ---------------------------------------------------------------- баны --
    def ban_stats(self, rank_tier: int | None = None, limit: int = 100) -> list[Row]:
        """Свежие строки ``vetmo_ban_stats`` (опционально по рангу)."""
        if limit <= 0:
            return []
        filters = None if rank_tier is None else {"rank_tier": int(rank_tier)}
        return self._gateway.select(
            "vetmo_ban_stats",
            filters=filters,
            order=("snapshot_date", True),
            limit=int(limit),
        )

    # ----------------------------------------------------------- служебное --
    def _resolve_patch_id(self, patch_id: int | None) -> int | None:
        if patch_id is not None:
            return int(patch_id)
        return _as_int((self.latest_patch() or {}).get("id"))


__all__ = ["META_WINDOW_DAYS", "AdminRepository"]
