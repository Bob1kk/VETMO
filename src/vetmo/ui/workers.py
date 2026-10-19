"""Воркеры для QThreadPool: долгие операции вне UI-потока (план §9)."""

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal


class WorkerSignals(QObject):
    """Сигналы результата: done (объект/None) и failed (текст ошибки)."""

    done = Signal(object)
    failed = Signal(str)


# PySide6 не передаёт владение QRunnable в QThreadPool: как только внешняя
# ссылка умирает, GC может снести Worker вместе с WorkerSignals РАНЬШЕ
# доставки queued-сигнала — коллбеки on_done/on_fail теряются
# недетерминированно. Реестр удерживает ссылку до доставки результата
# (cleanup-слот). Незавершённые воркеры (hang) остаются в реестре — это
# осознанный компромисс в пользу надёжности доставки сигналов.
_waited: list["Worker"] = []


def _release_ref(worker: "Worker") -> None:
    """Снимает удержание ссылки на воркер после доставки done/failed."""
    try:
        _waited.remove(worker)
    except ValueError:
        pass


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
        self.signals = WorkerSignals()
        if on_done is not None:
            self.connect_done(on_done)
        if on_fail is not None:
            self.connect_fail(on_fail)
        # cleanup-слоты срабатывают на доставке результата (GUI-поток),
        # поэтому ссылка живёт ровно до конца доставки queued-сигналов.
        self.signals.done.connect(lambda *_: _release_ref(self))
        self.signals.failed.connect(lambda *_: _release_ref(self))

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
    _waited.append(worker)  # удержание до доставки done/failed
    QThreadPool.globalInstance().start(worker)
    return worker
