"""Воркеры для QThreadPool: долгие операции вне UI-потока (план §9)."""

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal


class WorkerSignals(QObject):
    """Сигналы результата: done (объект/None) и failed (текст ошибки)."""

    done = Signal(object)
    failed = Signal(str)


class Worker(QRunnable):
    """QRunnable-обёртка над произвольной функцией (сеть/БД/CV)."""

    def __init__(
        self, fn: Callable[..., Any], *args: Any,
        on_done: Callable[[Any], None] | None = None,
        on_fail: Callable[[str], None] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs
        self._on_done = on_done
        self._on_fail = on_fail
        self.signals = WorkerSignals()

    def run(self) -> None:  # pragma: no cover - выполняется в worker-потоке
        """Выполняет функцию; результат/ошибка возвращаются через сигнал."""
        try:
            result = self._fn(*self._args, **self._kwargs)
        except Exception as exc:  # noqa: BLE001 — ошибка сети/БД не роняет GUI
            self.signals.failed.emit(f"{type(exc).__name__}: {exc}")
        else:
            self.signals.done.emit(result)

    def connect_done(self, on_done: Callable[[Any], None]) -> "Worker":
        """Подключает колбэк успеха (вызывается в UI-потоке через сигнал)."""
        self._on_done = on_done
        self.signals.done.connect(on_done)
        return self

    def connect_fail(self, on_fail: Callable[[str], None]) -> "Worker":
        """Подключает колбэк ошибки (вызывается в UI-потоке через сигнал)."""
        self._on_fail = on_fail
        self.signals.failed.connect(on_fail)
        return self


def start_worker(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Worker:
    """Создаёт Worker, стартует в глобальном пуле и возвращает его."""
    worker = Worker(fn, *args, **kwargs)
    QThreadPool.globalInstance().start(worker)
    return worker
