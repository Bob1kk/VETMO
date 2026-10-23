"""Вкладка «Обзор»: патч, последний запуск и быстрый запуск sync (T-104)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from vetmo.admin.tabs.common import (
    SyncState,
    format_age,
    format_datetime,
    format_int,
    status_text,
)
from vetmo.admin.workers import MODE_DRY, MODE_FULL, MODE_META, SyncRunner
from vetmo.ui.workers import start_worker

if TYPE_CHECKING:
    from vetmo.admin.context import AdminContext

MODE_LABELS: dict[str, str] = {
    MODE_META: "Обновить мету",
    MODE_FULL: "Полный sync",
    MODE_DRY: "Dry-run",
}

_CONFIRMATIONS: dict[str, str] = {
    MODE_META: (
        "Запустить обновление меты за последние 7 дней?\n\n"
        "Данные будут записаны в Supabase от имени service_role."
    ),
    MODE_FULL: (
        "Запустить полный sync: мета и матчапы?\n\n"
        "Запись в Supabase может занять несколько минут. "
        "Прогресс и лог — на вкладке «Синхронизация»."
    ),
    MODE_DRY: (
        "Запустить dry-run?\n\n"
        "Данные будут получены из STRATZ, но в Supabase не записываются."
    ),
}


def _details(run: dict[str, Any] | None) -> dict[str, Any]:
    """Разбирает jsonb ``details`` в dict (PostgREST может вернуть строку)."""
    if not run:
        return {}
    raw = run.get("details")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        import json

        try:
            parsed = json.loads(raw)
        except ValueError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


class _Card(QFrame):
    """Карточка со значением и подписью."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("statCard")
        self._title = QLabel(title, self)
        self._title.setObjectName("statLabel")
        self._value = QLabel("—", self)
        self._value.setObjectName("statValue")
        self._value.setWordWrap(True)
        self._detail = QLabel("", self)
        self._detail.setObjectName("mutedSmall")
        self._detail.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(3)
        layout.addWidget(self._title)
        layout.addWidget(self._value)
        layout.addWidget(self._detail)

    def set_value(self, value: str, detail: str = "", tooltip: str = "") -> None:
        """Обновляет значение/подпись карточки."""
        self._value.setText(value or "—")
        self._detail.setText(detail)
        self._detail.setToolTip(tooltip)

    def value_label(self) -> QLabel:
        """Лейбл значения (для смоук-тестов)."""
        return self._value


class DashboardTab(QWidget):
    """Сводка по БД и кнопки запуска sync с подтверждением."""

    status_message = Signal(str)

    def __init__(
        self,
        context: AdminContext,
        sync_state: SyncState,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._ctx = context
        self._state = sync_state
        self._runner: SyncRunner | None = None
        self._refresh_gen = 0

        self._cards: dict[str, _Card] = {}
        self._start_buttons: list[QPushButton] = []
        self._refresh_button: QPushButton | None = None
        self._build_ui()
        self._state.busy_changed.connect(self._set_busy)
        self.refresh()

    # ---------------------------------------------------------------- UI --
    def _build_ui(self) -> None:
        title = QLabel("Обзор", self)
        title.setObjectName("h1")
        subtitle = QLabel(
            "Состояние reference-данных Supabase и запуск обновления из STRATZ.",
            self,
        )
        subtitle.setObjectName("muted")
        subtitle.setWordWrap(True)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)
        cards = (
            ("patch", "ТЕКУЩИЙ ПАТЧ"),
            ("run", "ПОСЛЕДНИЙ ЗАПУСК"),
            ("fresh", "СВЕЖЕСТЬ ДАННЫХ"),
            ("errors", "ОШИБКИ"),
            ("meta", "СТРОК МЕТЫ"),
            ("matchups", "СТРОК МАТЧАПОВ"),
            ("period", "КОНЕЦ ПЕРИОДА"),
            ("trigger", "ИСТОЧНИК ЗАПУСКА"),
        )
        for index, (key, label) in enumerate(cards):
            card = _Card(label, self)
            self._cards[key] = card
            grid.addWidget(card, index // 4, index % 4)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        for mode in (MODE_META, MODE_FULL, MODE_DRY):
            button = QPushButton(MODE_LABELS[mode], self)
            button.setObjectName("primary" if mode == MODE_FULL else "secondary")
            button.clicked.connect(lambda _=False, m=mode: self._request_sync(m))
            self._start_buttons.append(button)
            buttons.addWidget(button)
        buttons.addStretch(1)
        self._refresh_button = QPushButton("Перечитать из БД", self)
        self._refresh_button.setObjectName("secondary")
        self._refresh_button.setToolTip("Только чтение: патч и последний запуск")
        self._refresh_button.clicked.connect(self.refresh)
        buttons.addWidget(self._refresh_button)

        self._hint = QLabel(
            "Кнопки запускают sync с service_role. Dry-run ничего не записывает.",
            self,
        )
        self._hint.setObjectName("mutedSmall")
        self._hint.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addLayout(grid)
        layout.addLayout(buttons)
        layout.addWidget(self._hint)
        layout.addStretch(1)

    # ------------------------------------------------------------- данные --
    def refresh(self) -> None:
        """Читает патч и последний run в фоне (сеть не блокирует UI)."""
        self._refresh_gen += 1
        generation = self._refresh_gen
        self.status_message.emit("Читаем состояние БД…")

        def job() -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
            return self._ctx.repository.latest_patch(), self._ctx.repository.last_run()

        def done(result: tuple[dict[str, Any] | None, dict[str, Any] | None]) -> None:
            if generation != self._refresh_gen:
                return
            patch, run = result
            self._apply_patch(patch)
            self._apply_run(run)
            if run is None:
                self.status_message.emit("Данные загружены: запусков sync пока нет")
            else:
                self.status_message.emit(
                    f"Данные загружены: последний запуск #{run.get('id', '—')} "
                    f"({status_text(run.get('status'))})"
                )

        def fail(message: str) -> None:
            if generation != self._refresh_gen:
                return
            self._cards["patch"].set_value("—", f"Ошибка: {message}")
            self._cards["run"].set_value("—", "Не удалось прочитать историю")
            self.status_message.emit(f"Ошибка чтения БД: {message}")

        start_worker(job, on_done=done, on_fail=fail)

    def _apply_patch(self, patch: dict[str, Any] | None) -> None:
        card = self._cards["patch"]
        if not patch:
            card.set_value("нет данных", "Патчи ещё не записаны")
            return
        version = str(patch.get("version") or "—")
        details = [f"id {patch.get('id', '—')}"]
        if patch.get("release_date"):
            details.append(f"выпущен {patch['release_date']}")
        if patch.get("is_current"):
            details.append("текущий")
        card.set_value(version, " · ".join(details))

    def _apply_run(self, run: dict[str, Any] | None) -> None:
        details = _details(run)
        if not run:
            for key in ("run", "fresh", "errors", "meta", "matchups", "period", "trigger"):
                self._cards[key].set_value("—", "запусков не было")
            return

        status = run.get("status")
        time_value = run.get("finished_at") or run.get("started_at")
        self._cards["run"].set_value(
            status_text(status),
            f"{format_datetime(time_value)} · {run.get('trigger_source') or run.get('source') or '—'}",
        )
        self._cards["fresh"].set_value(
            format_age(time_value),
            f"обновлено {format_datetime(time_value)}",
        )

        raw_errors = details.get("errors")
        errors: list[Any] = (
            list(raw_errors) if isinstance(raw_errors, list) else []
        )
        error_text = str(run.get("error") or "").strip()
        if error_text and error_text not in errors:
            errors = [error_text, *errors]
        self._cards["errors"].set_value(
            format_int(len(errors)) if errors else "0",
            "ошибок нет" if not errors else "первые: " + "; ".join(map(str, errors[:2])),
            "\n".join(map(str, errors[:10])),
        )
        self._cards["meta"].set_value(format_int(run.get("rows_meta")), "строк меты")
        self._cards["matchups"].set_value(
            format_int(run.get("rows_matchups")), "строк матчапов",
        )
        self._cards["period"].set_value(
            str(details.get("period_end") or "—"),
            "конец окна 7 дней" if details.get("period_end") else "период не указан",
        )
        self._cards["trigger"].set_value(
            str(run.get("trigger_source") or run.get("source") or "—"),
            f"request_id: {run.get('request_id') or '—'}",
        )

    # --------------------------------------------------------------- sync --
    def _request_sync(self, mode: str) -> None:
        """Подтверждение и запуск выбранного режима."""
        if self._state.is_busy or self._runner is not None:
            self.status_message.emit("Синхронизация уже выполняется")
            return
        answer = QMessageBox.question(
            self,
            "Подтверждение синхронизации",
            _CONFIRMATIONS[mode],
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            self.status_message.emit("Запуск отменён")
            return
        self._start(mode)

    def _start(self, mode: str) -> None:
        runner = SyncRunner(mode, self._ctx, self)
        self._runner = runner
        runner.progress.connect(self._on_progress)
        runner.finished.connect(self._on_finished)
        runner.failed.connect(self._on_failed)
        self._state.set_busy(True)
        self.status_message.emit(f"Запущен sync: {MODE_LABELS.get(mode, mode)}")
        runner.start()

    def _on_progress(self, message: str) -> None:
        text = str(message).strip()
        if text:
            self.status_message.emit(text)

    def _on_finished(self, summary: dict[str, Any]) -> None:
        runner = self._runner
        self._runner = None
        self._state.set_busy(False)
        if runner is not None:
            runner.wait(2000)
            runner.deleteLater()

        errors = summary.get("errors") or []
        lines = [
            f"Режим: {summary.get('mode', '—')}",
            f"Патч: {summary.get('patch_version') or summary.get('patch_id') or '—'}",
            f"Строк меты: {format_int(summary.get('rows_meta'))}",
            f"Строк матчапов: {format_int(summary.get('rows_matchups'))}",
            f"Статус: {status_text(summary.get('status'))}",
        ]
        if errors:
            lines.append("Ошибки:")
            lines.extend(f"· {item}" for item in list(errors)[:5])
        QMessageBox.information(
            self,
            "Синхронизация завершена",
            "\n".join(lines),
        )
        self.status_message.emit(
            f"Sync завершён: {status_text(summary.get('status'))}, "
            f"мета {format_int(summary.get('rows_meta'))}"
        )
        self.refresh()

    def _on_failed(self, message: str) -> None:
        runner = self._runner
        self._runner = None
        self._state.set_busy(False)
        if runner is not None:
            runner.wait(2000)
            runner.deleteLater()
        QMessageBox.critical(
            self,
            "Ошибка синхронизации",
            f"Sync не выполнен:\n{message}",
        )
        self.status_message.emit(f"Ошибка sync: {message}")

    def _set_busy(self, busy: bool) -> None:
        for button in self._start_buttons:
            button.setEnabled(not busy)
        if self._refresh_button is not None:
            self._refresh_button.setEnabled(not busy)

    # ------------------------------------------------------------ служебное --
    def running_mode(self) -> str | None:
        """Режим активного runner'а или None (для смоука)."""
        return self._runner.mode if self._runner is not None else None

    def shutdown(self) -> bool:
        """Останавливает активный sync при закрытии окна.

        Возвращает ``True``, если поток завершился (или его не было).
        """
        if self._runner is None:
            return True
        self._runner.cancel()
        if self._runner.isRunning():
            return self._runner.wait(5000)
        return True


__all__ = ["DashboardTab", "MODE_LABELS"]
