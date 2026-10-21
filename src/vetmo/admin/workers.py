"""QThread-обёртка над ``sync_all`` для VETMO Admin.

``sync_all`` синхронный, поэтому запускается в отдельном потоке: UI остаётся
отзывчивым, прогресс приходит сигналом ``progress``. Отмена кооперативная —
``sync_all`` проверяет ``should_stop`` между срезами.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from uuid import uuid4

from PySide6.QtCore import QObject, QThread, Signal

from vetmo.services.stratz_sync import SyncStats, sync_all

if TYPE_CHECKING:
    from vetmo.admin.context import AdminContext

logger = logging.getLogger("vetmo.admin.workers")

MODE_META = "meta"
MODE_FULL = "full"
MODE_DRY = "dry"
MODES: tuple[str, ...] = (MODE_META, MODE_FULL, MODE_DRY)

TRIGGER = "admin-app"


class SyncRunner(QThread):
    """Выполняет ``sync_all`` в фоне и транслирует результат в сигналы."""

    progress = Signal(str)
    # Внимание: перекрывает QThread.finished() — сюда приходит dict-итог.
    finished = Signal(dict)
    failed = Signal(str)

    def __init__(
        self,
        mode: str,
        context: AdminContext,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        if mode not in MODES:
            raise ValueError(
                f"Неизвестный режим sync: {mode!r}; ожидался один из {MODES}"
            )
        self._mode = mode
        self._context = context
        self._stop = False
        self._request_id = uuid4().hex[:12]

    # ------------------------------------------------------------ свойства --
    @property
    def mode(self) -> str:
        return self._mode

    @property
    def request_id(self) -> str:
        return self._request_id

    @property
    def context(self) -> AdminContext:
        """Контекст, с которым создан runner (для вкладок и логов)."""
        return self._context

    # ------------------------------------------------------------------ run --
    def run(self) -> None:
        """Точка входа потока: ошибки не выбрасываются, а уходят в ``failed``."""
        dry_run = self._mode == MODE_DRY
        include_matchups = self._mode == MODE_FULL
        try:
            stats = sync_all(
                dry_run=dry_run,
                include_matchups=include_matchups,
                progress=self.progress.emit,
                trigger=TRIGGER,
                request_id=self._request_id,
                should_stop=self._should_stop,
            )
        except Exception as exc:  # noqa: BLE001 - UI должен увидеть причину
            logger.exception("Admin sync завершился ошибкой (%s)", self._request_id)
            self.failed.emit(f"{type(exc).__name__}: {exc}")
            return
        self.finished.emit(self._summary(stats))

    def _summary(self, stats: SyncStats) -> dict[str, object]:
        cancelled = self._stop
        status = "partial" if (stats.errors or cancelled) else "ok"
        return {
            "mode": self._mode,
            "trigger": TRIGGER,
            "request_id": self._request_id,
            "patch_id": stats.patch_id,
            "patch_version": stats.patch_version,
            "rows_meta": stats.rows_meta,
            "rows_matchups": stats.rows_matchups,
            "slices": stats.slices,
            "period": stats.period,
            "errors": list(stats.errors),
            "status": status,
            "cancelled": cancelled,
        }

    # --------------------------------------------------------------- отмена --
    def cancel(self) -> None:
        """Запросить остановку: текущий срез дописывается, новые не начинаются."""
        self._stop = True
        logger.info("Admin sync: запрошена отмена (%s)", self._request_id)

    def _should_stop(self) -> bool:
        return self._stop


__all__ = ["MODE_DRY", "MODE_FULL", "MODE_META", "MODES", "SyncRunner"]
