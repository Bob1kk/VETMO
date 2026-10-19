"""KV-репозиторий настроек (ON CONFLICT по key). Контракт T-005."""

from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from vetmo.data.models_orm import UserSettingORM


class SettingsRepository:
    """Настройки оверлея/тем: строковое KV-хранилище."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, key: str) -> str | None:
        """Значение по ключу или None."""
        row = (
                self._session.query(UserSettingORM)
                .filter(UserSettingORM.key == key)
                .first()
            )
        return row.value if row else None

    def set(self, key: str, value: str) -> None:
        """Записывает значение; повторный set перезаписывает (ON CONFLICT)."""
        stmt = sqlite_insert(UserSettingORM).values(key=key, value=value)
        stmt = stmt.on_conflict_do_update(
            index_elements=["key"], set_={"value": stmt.excluded.value})
        self._session.execute(stmt)
        self._session.commit()
