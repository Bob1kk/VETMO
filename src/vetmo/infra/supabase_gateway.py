"""Supabase REST/Auth gateway для приложения.

Приложение использует только publishable/anon key. service_role сюда не
передаётся: запись reference-данных выполняет отдельный sync-скрипт.

Клиент создаётся лениво и отдельно на каждый поток: чтения из UI идут через
QThreadPool, а supabase-py/httpx-клиент не стоит делить между потоками без
необходимости. Токены сессии хранятся в памяти и в
%APPDATA%/VETMO/supabase_session.json.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any, TypeVar

import httpx
from supabase import Client, create_client
from supabase.lib.client_options import SyncClientOptions

from vetmo.infra.config import Settings
from vetmo.infra.http_client import build_http_client
from vetmo.infra.proxy import system_proxy_url

logger = logging.getLogger("vetmo.supabase")
T = TypeVar("T")

_SESSION_FILE = "supabase_session.json"
_RETRY_ATTEMPTS = 2
_RETRY_DELAYS = (0.5, 1.0)
# Таймаут запроса к Supabase. 45 с давали «зависший» UI при троттлинге
# проекта: один медленный select стоил до 135 с (45 × 3 попытки).
_REQUEST_TIMEOUT_S = 20.0


def _appdata_dir() -> Path:
    """Каталог данных приложения на Windows (или ~/.local/share на других ОС)."""
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "VETMO"
    return Path.home() / ".local" / "share" / "VETMO"


def _session_path() -> Path:
    return _appdata_dir() / _SESSION_FILE


def _as_dict(row: Any) -> dict[str, Any]:
    """Привести строку JSON ответа Supabase к dict[str, Any]."""
    if isinstance(row, dict):
        return row  # type: ignore[return-value]
    return {}


def _is_retryable(exc: Exception) -> bool:
    """Сетевые/временные ошибки, которые имеет смысл повторить."""
    if isinstance(exc, (httpx.TransportError, httpx.TimeoutException, ConnectionError)):
        return True
    status = getattr(exc, "status_code", None)
    if status is None:
        text = str(exc)
        for code in ("429", "500", "502", "503", "504"):
            if code in text:
                return True
        return False
    try:
        return int(status) == 429 or 500 <= int(status) < 600
    except (TypeError, ValueError):
        return False


class SupabaseGateway:
    """Тонкая обёртка над supabase-py с anon-ключом и anonymous auth."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._url = (settings.supabase_url or "").rstrip("/")
        self._key = settings.supabase_publishable_key or ""
        self._local = threading.local()
        self._auth_lock = threading.Lock()
        self._auth_attempted = False
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._user_id: str | None = None
        self._load_session_file()

        proxy = system_proxy_url()
        if proxy:
            # supabase-py создаёт httpx.Client с trust_env=True; этого достаточно
            # для системного прокси, но выставляем и переменные для надёжности.
            os.environ.setdefault("HTTPS_PROXY", proxy)
            os.environ.setdefault("HTTP_PROXY", proxy)

    # ------------------------------------------------------------------
    # Состояние
    # ------------------------------------------------------------------

    @property
    def is_configured(self) -> bool:
        """Заданы ли URL и publishable-ключ."""
        return bool(self._url and self._key)

    @property
    def user_id(self) -> str | None:
        """id текущего anonymous-пользователя, если auth доступен."""
        return self._user_id

    def _client(self) -> Client:
        client = getattr(self._local, "client", None)
        if client is None:
            if not self.is_configured:
                raise RuntimeError(
                    "Supabase не настроен: задайте VETMO_SUPABASE_URL и "
                    "VETMO_SUPABASE_ANON_KEY."
                )
            client = create_client(
                self._url,
                self._key,
                options=SyncClientOptions(
                    auto_refresh_token=True,
                    persist_session=False,
                    postgrest_client_timeout=_REQUEST_TIMEOUT_S,
                    httpx_client=build_http_client(
                        timeout=_REQUEST_TIMEOUT_S),
                ),
            )
            self._local.client = client
            if self._access_token and self._refresh_token:
                try:
                    client.auth.set_session(self._access_token, self._refresh_token)
                except Exception as exc:  # noqa: BLE001 - сессия могла истечь
                    logger.info("Supabase session restore skipped: %s", type(exc).__name__)
        return client

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def _load_session_file(self) -> None:
        path = _session_path()
        if not path.is_file():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self._access_token = data.get("access_token")
            self._refresh_token = data.get("refresh_token")
            self._user_id = data.get("user_id")
        except (OSError, ValueError):
            logger.warning("Не удалось прочитать Supabase session file")

    def _save_session_file(self) -> None:
        if not self._access_token or not self._refresh_token:
            return
        path = _session_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(
                    {
                        "access_token": self._access_token,
                        "refresh_token": self._refresh_token,
                        "user_id": self._user_id,
                    }
                ),
                encoding="utf-8",
            )
        except OSError:
            logger.warning("Не удалось сохранить Supabase session file")

    def ensure_session(self) -> str | None:
        """Восстанавливает/создаёт anonymous-сессию.

        Возвращает user_id или None, если anonymous auth выключен/недоступен.
        Reference-данные при этом всё равно доступны через anon key.
        """
        if self._user_id:
            return self._user_id
        with self._auth_lock:
            if self._user_id:
                return self._user_id
            if self._auth_attempted:
                return None
            self._auth_attempted = True
            try:
                client = self._client()
                if self._access_token and self._refresh_token:
                    try:
                        client.auth.set_session(self._access_token, self._refresh_token)
                        session = client.auth.get_session()
                        if session and session.user:
                            self._user_id = str(session.user.id)
                            return self._user_id
                    except Exception:  # noqa: BLE001 - пробуем anonymous sign-in
                        pass
                response = client.auth.sign_in_anonymously()
                session = getattr(response, "session", None)
                user = getattr(response, "user", None)
                if session and user:
                    self._access_token = session.access_token
                    self._refresh_token = session.refresh_token
                    self._user_id = str(user.id)
                    self._save_session_file()
                    return self._user_id
            except Exception as exc:  # noqa: BLE001 - auth не должен ронять UI
                logger.info("Anonymous auth недоступен: %s", type(exc).__name__)
            return None

    # ------------------------------------------------------------------
    # Низкоуровневые операции
    # ------------------------------------------------------------------

    def _run(self, operation: str, fn: Callable[[], T]) -> T:
        last: Exception | None = None
        for attempt in range(_RETRY_ATTEMPTS):
            try:
                return fn()
            except Exception as exc:  # noqa: BLE001 - классифицируем ниже
                last = exc
                if attempt >= _RETRY_ATTEMPTS - 1 or not _is_retryable(exc):
                    raise
                logger.info("Supabase retry %s (%s/%s)", operation, attempt + 1, _RETRY_ATTEMPTS)
                time.sleep(_RETRY_DELAYS[min(attempt, len(_RETRY_DELAYS) - 1)])
        assert last is not None  # pragma: no cover
        raise last

    @staticmethod
    def _apply_filters(query: Any, filters: dict[str, Any] | None) -> Any:
        if not filters:
            return query
        for key, value in filters.items():
            if isinstance(value, tuple) and len(value) == 2:
                op, operand = value
                if op == "in":
                    query = query.in_(key, operand)
                elif op == "gte":
                    query = query.gte(key, operand)
                elif op == "lte":
                    query = query.lte(key, operand)
                elif op == "neq":
                    query = query.neq(key, operand)
                else:
                    query = query.eq(key, operand)
            elif isinstance(value, list):
                query = query.in_(key, value)
            else:
                query = query.eq(key, value)
        return query

    def select(
        self,
        table: str,
        *,
        columns: str = "*",
        filters: dict[str, Any] | None = None,
        order: tuple[str, bool] | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[dict[str, Any]]:
        """SELECT из таблицы/представления (offset — для страниц > 1000)."""
        def call() -> list[dict[str, Any]]:
            query = self._client().table(table).select(columns)
            query = self._apply_filters(query, filters)
            if order:
                query = query.order(order[0], desc=order[1])
            if offset is not None:
                start = max(0, int(offset))
                size = max(1, int(limit)) if limit is not None else 1000
                query = query.range(start, start + size - 1)
            elif limit is not None:
                query = query.limit(limit)
            response = query.execute()
            return list(response.data or [])

        return self._run(f"select:{table}", call)

    def rpc(self, name: str, params: dict[str, Any]) -> Any:
        """Вызов RPC-функции."""
        def call() -> Any:
            response = self._client().rpc(name, params).execute()
            return response.data

        return self._run(f"rpc:{name}", call)

    def insert(self, table: str, rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
        """INSERT строк."""
        payload = list(rows)
        if not payload:
            return []

        def call() -> list[dict[str, Any]]:
            response = self._client().table(table).insert(payload).execute()
            return [_as_dict(row) for row in (response.data or [])]

        return self._run(f"insert:{table}", call)

    def upsert(
        self,
        table: str,
        rows: Iterable[dict[str, Any]],
        *,
        on_conflict: str | None = None,
    ) -> list[dict[str, Any]]:
        """UPSERT строк (батчи по 500)."""
        payload = list(rows)
        if not payload:
            return []
        result: list[dict[str, Any]] = []
        for start in range(0, len(payload), 500):
            chunk = payload[start : start + 500]

            def call(chunk: list[dict[str, Any]] = chunk) -> list[dict[str, Any]]:
                response = (
                    self._client()
                    .table(table)
                    .upsert(chunk, on_conflict=on_conflict or "")
                    .execute()
                )
                return [_as_dict(row) for row in (response.data or [])]

            result.extend(self._run(f"upsert:{table}", call))
        return result

    def update(
        self,
        table: str,
        values: dict[str, Any],
        filters: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """UPDATE по фильтрам."""
        def call() -> list[dict[str, Any]]:
            query = self._client().table(table).update(values)
            query = self._apply_filters(query, filters)
            response = query.execute()
            return list(response.data or [])

        return self._run(f"update:{table}", call)

    def delete(
        self,
        table: str,
        filters: dict[str, Any],
    ) -> int:
        """DELETE по фильтрам (только service_role в sync-скрипте)."""
        def call() -> int:
            query = self._client().table(table).delete()
            query = self._apply_filters(query, filters)
            response = query.execute()
            return len(response.data or [])

        return self._run(f"delete:{table}", call)

    def close(self) -> None:
        """Закрывает клиент текущего потока, если он создан."""
        client = getattr(self._local, "client", None)
        if client is not None:
            try:
                client.auth.close()
            except Exception:  # noqa: BLE001
                pass
            self._local.client = None


__all__ = ["SupabaseGateway"]
