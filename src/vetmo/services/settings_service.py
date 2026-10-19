"""Настройки оверлея/тем/приоритетов через SettingsRepository. Контракт T-009."""

import json

from sqlalchemy.orm import Session, sessionmaker

from vetmo.data.repositories.settings_repo import SettingsRepository

_KEY_POS_X = "overlay_position_x"
_KEY_POS_Y = "overlay_position_y"
_KEY_OPACITY = "overlay_opacity"
_KEY_THEME = "overlay_theme"
_KEY_CLICK = "overlay_click_through"
_KEY_SHOW_DIRE = "overlay_show_dire"
_KEY_PRIORITIES = "position_priorities"

_VALID_THEMES = ("dark", "light")


class SettingsService:
    """Сервис настроек: читает/пишет user_settings через репозиторий."""

    def __init__(self, sessionmaker: sessionmaker[Session]) -> None:
        self._sessionmaker = sessionmaker

    def _repo(self) -> tuple[SettingsRepository, Session]:
        """Открывает сессию и возвращает (репозиторий, сессию)."""
        session = self._sessionmaker()
        return SettingsRepository(session), session

    def _get(self, key: str, default: str | None = None) -> str | None:
        """Получить значение настройки."""
        repo, session = self._repo()
        try:
            value = repo.get(key)
            return value if value is not None else default
        finally:
            session.close()

    def _set(self, key: str, value: str) -> None:
        """Записать значение настройки."""
        repo, session = self._repo()
        try:
            repo.set(key, value)
        finally:
            session.close()

    # --- Позиция оверлея ---
    def get_overlay_position(self) -> tuple[int, int]:
        """(x, y), дефолт (20, 20)."""
        x = int(self._get(_KEY_POS_X, "20") or 20)
        y = int(self._get(_KEY_POS_Y, "20") or 20)
        return x, y

    def set_overlay_position(self, x: int, y: int) -> None:
        """Сохраняет позицию оверлея."""
        self._set(_KEY_POS_X, str(int(x)))
        self._set(_KEY_POS_Y, str(int(y)))

    # --- Прозрачность ---
    def get_opacity(self) -> float:
        """0.0..1.0, дефолт 0.85."""
        try:
            return float(self._get(_KEY_OPACITY, "0.85") or 0.85)
        except ValueError:
            return 0.85

    def set_opacity(self, value: float) -> None:
        """Сохраняет прозрачность, кламп в [0.0, 1.0]."""
        clamped = max(0.0, min(1.0, float(value)))
        self._set(_KEY_OPACITY, repr(clamped))

    # --- Тема ---
    def get_theme(self) -> str:
        """'dark' | 'light', дефолт 'dark'."""
        theme = self._get(_KEY_THEME, "dark") or "dark"
        return theme if theme in _VALID_THEMES else "dark"

    def set_theme(self, theme: str) -> None:
        """Сохраняет тему; недопустимая -> ValueError."""
        if theme not in _VALID_THEMES:
            raise ValueError(f"Недопустимая тема (invalid theme): {theme}")
        self._set(_KEY_THEME, theme)

    # --- Флаги оверлея ---
    def get_click_through(self) -> bool:
        """Дефолт True."""
        return (self._get(_KEY_CLICK, "1") or "1") == "1"

    def set_click_through(self, flag: bool) -> None:
        """Сохраняет click-through."""
        self._set(_KEY_CLICK, "1" if flag else "0")

    def get_show_dire(self) -> bool:
        """Показывать колонку Dire; дефолт True."""
        return (self._get(_KEY_SHOW_DIRE, "1") or "1") == "1"

    def set_show_dire(self, flag: bool) -> None:
        """Сохраняет флаг Dire."""
        self._set(_KEY_SHOW_DIRE, "1" if flag else "0")

    # --- Приоритеты позиций (game-agent) ---
    def get_position_priorities(self) -> dict[int, list[int]]:
        """Позиция 1..5 -> список hero_id в порядке предпочтения."""
        raw = self._get(_KEY_PRIORITIES, None)
        if not raw:
            return {}
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            return {}
        if not isinstance(data, dict):
            return {}
        result: dict[int, list[int]] = {}
        for key, ids in data.items():
            try:
                position = int(key)
            except (TypeError, ValueError):
                continue
            if 1 <= position <= 5:
                result[position] = [int(x) for x in ids if int(x) >= 1]
        return result

    def set_position_priorities(self, priorities: dict[int, list[int]]) -> None:
        """Сохраняет приоритеты; валидные позиции 1..5, hero_id >= 1."""
        clean: dict[int, list[int]] = {}
        for position, hero_ids in priorities.items():
            if 1 <= int(position) <= 5:
                ids = [int(h) for h in hero_ids if int(h) >= 1]
                clean[int(position)] = ids
        self._set(_KEY_PRIORITIES, json.dumps(clean, ensure_ascii=False))
