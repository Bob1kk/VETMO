"""Настройки пользователя: Supabase (anonymous auth) + локальный JSON-фолбэк.

Почему фолбэк: Anonymous Sign-Ins могут быть выключены в проекте Supabase.
Приложение не должно терять настройки и падать; как только auth включён и
таблица ``vetmo_profiles`` создана, настройки автоматически уходят в облако.
Локальный файл — не SQLite и не второй источник мета-данных.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from vetmo.infra.supabase_gateway import SupabaseGateway

logger = logging.getLogger("vetmo.settings")

_PROFILE_COLUMNS = (
    "user_id,overlay_x,overlay_y,opacity,theme,click_through,show_dire,"
    "display_index"
)

_DEFAULTS: dict[str, Any] = {
    "overlay_x": 20,
    "overlay_y": 20,
    "opacity": 0.85,
    "theme": "dark",
    "click_through": False,
    "show_dire": True,
    "display_index": -1,
}


def _settings_path() -> Path:
    appdata = os.environ.get("APPDATA")
    base = Path(appdata) if appdata else Path.home() / ".local" / "share"
    return base / "VETMO" / "settings.json"


class SupabaseSettingsService:
    """Тот же контракт, что SettingsService, но данные в Supabase."""

    def __init__(self, gateway: SupabaseGateway) -> None:
        self._gateway = gateway
        self._profile: dict[str, Any] | None = None
        self._remote_disabled = False
        self._local = self._read_local()

    # ------------------------------------------------------------ служебное --
    @property
    def remote_enabled(self) -> bool:
        """True, если профиль реально читается/пишется в Supabase."""
        return self._profile is not None and not self._remote_disabled

    def _read_local(self) -> dict[str, Any]:
        path = _settings_path()
        if not path.is_file():
            return dict(_DEFAULTS)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return dict(_DEFAULTS)
            merged = dict(_DEFAULTS)
            merged.update(data)
            return merged
        except (OSError, ValueError):
            return dict(_DEFAULTS)

    def _write_local(self) -> None:
        path = _settings_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(self._local, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            logger.warning("Не удалось сохранить локальные настройки")

    def _ensure_remote(self) -> dict[str, Any] | None:
        """Читает/создаёт профиль один раз; ошибка -> локальный режим."""
        if self._profile is not None:
            return None if self._remote_disabled else self._profile
        if not self._gateway.is_configured or self._remote_disabled:
            return None
        user_id = self._gateway.ensure_session()
        if not user_id:
            return None
        try:
            rows = self._gateway.select(
                "vetmo_profiles",
                columns=_PROFILE_COLUMNS,
                filters={"user_id": user_id},
                limit=1,
            )
            if rows:
                self._profile = rows[0]
            else:
                inserted = self._gateway.insert(
                    "vetmo_profiles",
                    [{"user_id": user_id, **_DEFAULTS}],
                )
                self._profile = inserted[0] if inserted else {"user_id": user_id, **_DEFAULTS}
            # пустые/None-поля не должны ломать getters
            for key, default in _DEFAULTS.items():
                if self._profile.get(key) is None:
                    self._profile[key] = default
            return self._profile
        except Exception as exc:  # noqa: BLE001 - таблицы может ещё не быть
            self._remote_disabled = True
            logger.info("Профиль Supabase недоступен, локальные настройки: %s", type(exc).__name__)
            return None

    def _get(self, key: str) -> Any:
        remote = self._ensure_remote()
        source = remote if remote is not None else self._local
        return source.get(key, _DEFAULTS.get(key))

    def _update(self, **values: Any) -> None:
        self._local.update(values)
        self._write_local()
        remote = self._ensure_remote()
        if remote is None:
            return
        remote.update(values)
        user_id = remote.get("user_id")
        if not user_id:
            return
        try:
            self._gateway.update(
                "vetmo_profiles", values, {"user_id": user_id},
            )
        except Exception as exc:  # noqa: BLE001 - локальное значение уже сохранено
            logger.info("Настройка не ушла в Supabase: %s", type(exc).__name__)

    # ------------------------------------------------------------- позиция --
    def get_overlay_position(self) -> tuple[int, int]:
        """(x, y) относительно выбранного монитора; дефолт (20, 20)."""
        try:
            return int(self._get("overlay_x")), int(self._get("overlay_y"))
        except (TypeError, ValueError):
            return 20, 20

    def set_overlay_position(self, x: int, y: int) -> None:
        self._update(overlay_x=int(x), overlay_y=int(y))

    def get_monitor_index(self) -> int:
        """-1 = второй монитор, если есть, иначе основной; 0..N — явный выбор."""
        try:
            return int(self._get("display_index"))
        except (TypeError, ValueError):
            return -1

    def set_monitor_index(self, index: int) -> None:
        self._update(display_index=int(index))

    # ------------------------------------------------------- непрозрачность --
    def get_opacity(self) -> float:
        try:
            return float(self._get("opacity"))
        except (TypeError, ValueError):
            return 0.85

    def set_opacity(self, value: float) -> None:
        clamped = max(0.0, min(1.0, float(value)))
        self._update(opacity=round(clamped, 2))

    # --------------------------------------------------------------- тема --
    def get_theme(self) -> str:
        theme = str(self._get("theme") or "dark")
        return theme if theme in ("dark", "light") else "dark"

    def set_theme(self, theme: str) -> None:
        if theme not in ("dark", "light"):
            raise ValueError(f"Недопустимая тема (invalid theme): {theme}")
        self._update(theme=theme)

    # -------------------------------------------------------------- флаги --
    def get_click_through(self) -> bool:
        return bool(self._get("click_through"))

    def set_click_through(self, flag: bool) -> None:
        self._update(click_through=bool(flag))

    def get_show_dire(self) -> bool:
        return bool(self._get("show_dire"))

    def set_show_dire(self, flag: bool) -> None:
        self._update(show_dire=bool(flag))


__all__ = ["SupabaseSettingsService"]
