"""Опциональный Supabase клиент-заглушка (best-effort). Контракт T-016."""

import json as json_module
import logging
from typing import Any

import httpx
from sqlalchemy.orm import Session, sessionmaker

from vetmo.data.repositories.meta_repo import MetaRepository
from vetmo.infra.config import Settings
from vetmo.infra.http_client import build_http_client

logger = logging.getLogger("vetmo.supabase")


class SupabaseClient:
    """Отправка мета-снэпшотов в Supabase; без учётных данных — no-op."""

    def __init__(
        self, settings: Settings,
        sessionmaker: sessionmaker[Session] | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._settings = settings
        self._sessionmaker = sessionmaker
        self._http = http_client or build_http_client(settings.http_timeout)

    def sync_meta_snapshot(self, limit: int = 50) -> dict[str, Any]:
        """Отправляет топ мета-снэпшоты; ошибки глотаются (best-effort)."""
        if not self._settings.supabase_url or not self._settings.supabase_key:
            return {"enabled": False, "sent": 0}
        payload = self._collect_payload(limit)
        if not payload:
            return {"enabled": True, "sent": 0}
        sent = self._post(payload)
        return {"enabled": True, "sent": sent}

    def _collect_payload(self, limit: int) -> list[dict[str, Any]]:
        """Собирает мета-снэпшоты из БД (если доступна)."""
        if self._sessionmaker is None:
            return []
        try:
            with self._sessionmaker() as session:
                top = MetaRepository(session).get_top_meta(limit)
        except Exception as error:  # noqa: BLE001
            logger.warning("Supabase: не удалось собрать данные: %s", error)
            return []
        return [
            {
                "hero_id": row.hero_id,
                "hero_name": row.name,
                "win_rate": row.win_rate,
                "pick_rate": row.pick_rate,
                "ban_rate": row.ban_rate,
                "delta_win": row.delta_win,
                "delta_pick": row.delta_pick,
                "delta_ban": row.delta_ban,
                "positions": row.positions,
            }
            for row in top
        ]

    def _post(self, payload: list[dict[str, Any]]) -> int:
        """POST к REST: удачные записи считаем; ошибки — в лог, 0."""
        url = f"{self._settings.supabase_url}/rest/v1/vetmo_meta"
        headers = {
            "apikey": self._settings.supabase_key or "",
            "Authorization": f"Bearer {self._settings.supabase_key}",
            "Content-Type": "application/json",
        }
        try:
            response = self._http.post(
                url, headers=headers, content=json_module.dumps(payload))
            if response.status_code in (200, 201, 204):
                return len(payload)
            logger.warning(
                "Supabase sync: HTTP %s — данные не отправлены",
                response.status_code)
        except Exception as error:  # noqa: BLE001 — сеть не должна ронять GUI
            logger.warning("Supabase sync: сетевая ошибка: %s", error)
        return 0
