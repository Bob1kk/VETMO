"""Вкладка «Синхронизация»: режим, прогресс и живой лог (T-105)."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from vetmo.admin.tabs.common import SyncState, format_int, status_text
from vetmo.admin.workers import MODE_DRY, MODE_FULL, MODE_META, SyncRunner

if TYPE_CHECKING:
    from vetmo.admin.context import AdminContext

_MODE_ITEMS: tuple[tuple[str, str], ...] = (
    ("Мета за 7 дней", MODE_META),
    ("Полный sync (мета + матчапы)", MODE_FULL),
    ("Dry-run (без записи)", MODE_DRY),
)


class SyncTab(QWidget):
    """Ручной запуск ``sync_all`` в QThread с логом и отменой."""

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
        self._build_ui()
        self._state.busy_changed.connect(self._set_busy)
        self._set_busy(self._state.is_busy)

    # ---------------------------------------------------------------- UI --
    def _build_ui(self) -> None:
        title = QLabel("Синхронизация", self)
        title.setObjectName("h1")
        subtitle = QLabel(
            "Sync выполняется в отдельном потоке; интерфейс остаётся отзывчивым. "
            "Отмена кооперативная — текущий срез дописывается.",
            self,
        )
        subtitle.setObjectName("muted")
        subtitle.setWordWrap(True)

        self._mode = QComboBox(self)
        self._mode.setObjectName("filterCombo")
        for label, mode in _MODE_ITEMS:
            self._mode.addItem(label, mode)

        self._start_button = QPushButton("Запустить", self)
        self._start_button.setObjectName("primary")
        self._start_button.clicked.connect(self._start)
        self._cancel_button = QPushButton("Отменить", self)
        self._cancel_button.setObjectName("secondary")
        self._cancel_button.setEnabled(False)
        self._cancel_button.clicked.connect(self._cancel)

        controls = QHBoxLayout()
        controls.setSpacing(8)
        controls.addWidget(QLabel("Режим:", self))
        controls.addWidget(self._mode, 1)
        controls.addWidget(self._start_button)
        controls.addWidget(self._cancel_button)

        self._progress = QProgressBar(self)
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setTextVisible(True)

        self._state_label = QLabel("Готово к запуску", self)
        self._state_label.setObjectName("mutedSmall")

        self._log = QPlainTextEdit(self)
        self._log.setReadOnly(True)
        self._log.setMaximumBlockCount(5000)
        self._log.setPlaceholderText("Лог синхронизации появится здесь…")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addLayout(controls)
        layout.addWidget(self._progress)
        layout.addWidget(self._state_label)
        layout.addWidget(self._log, 1)

    # -------------------------------------------------------------- лог --
    def _append(self, message: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        self._log.appendPlainText(f"[{stamp}] {message}")
        bar = self._log.verticalScrollBar()
        bar.setValue(bar.maximum())

    def clear_log(self) -> None:
        """Очищает лог (для повторного запуска/тестов)."""
        self._log.clear()

    def log_text(self) -> str:
        """Текущее содержимое лога (для смоук-тестов)."""
        return self._log.toPlainText()

    # ------------------------------------------------------------- запуск --
    def _start(self) -> None:
        if self._state.is_busy or self._runner is not None:
            self.status_message.emit("Синхронизация уже выполняется")
            return
        mode = str(self._mode.currentData())
        runner = SyncRunner(mode, self._ctx, self)
        self._runner = runner
        runner.progress.connect(self._on_progress)
        runner.finished.connect(self._on_finished)
        runner.failed.connect(self._on_failed)

        self.clear_log()
        self._append(f"Запуск sync, режим: {self._mode.currentText()}")
        self._progress.setRange(0, 0)
        self._progress.setTextVisible(False)
        self._state.set_busy(True)
        self.status_message.emit(f"Синхронизация запущена: {self._mode.currentText()}")
        runner.start()

    def _cancel(self) -> None:
        if self._runner is None:
            return
        self._runner.cancel()
        self._cancel_button.setEnabled(False)
        self._append("Запрошена отмена: текущий срез будет дописан, новые не начнутся")
        self.status_message.emit("Запрошена отмена синхронизации")

    def _on_progress(self, message: str) -> None:
        text = str(message).strip()
        if text:
            self._append(text)
            self._state_label.setText(text)

    def _on_finished(self, summary: dict[str, Any]) -> None:
        runner = self._runner
        self._runner = None
        self._state.set_busy(False)
        if runner is not None:
            runner.wait(2000)
            runner.deleteLater()

        self._progress.setRange(0, 100)
        self._progress.setValue(100)
        self._progress.setTextVisible(True)
        self._state_label.setText(f"Завершено: {status_text(summary.get('status'))}")
        self._append("—" * 40)
        self._append(f"Итог: статус {status_text(summary.get('status'))}")
        self._append(
            f"Патч: {summary.get('patch_version') or summary.get('patch_id') or '—'}"
        )
        self._append(f"Строк меты: {format_int(summary.get('rows_meta'))}")
        self._append(f"Строк матчапов: {format_int(summary.get('rows_matchups'))}")
        self._append(f"Срезов: {format_int(summary.get('slices'))}")
        errors = summary.get("errors") or []
        if errors:
            self._append(f"Ошибки ({len(errors)}):")
            for item in list(errors)[:20]:
                self._append(f"  · {item}")
        else:
            self._append("Ошибок нет")
        self.status_message.emit(
            f"Синхронизация завершена: {status_text(summary.get('status'))}"
        )

    def _on_failed(self, message: str) -> None:
        runner = self._runner
        self._runner = None
        self._state.set_busy(False)
        if runner is not None:
            runner.wait(2000)
            runner.deleteLater()
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setTextVisible(True)
        self._state_label.setText("Ошибка синхронизации")
        self._append(f"ОШИБКА: {message}")
        QMessageBox.critical(
            self,
            "Ошибка синхронизации",
            f"Sync не выполнен:\n{message}",
        )
        self.status_message.emit(f"Ошибка sync: {message}")

    def _set_busy(self, busy: bool) -> None:
        self._start_button.setEnabled(not busy)
        self._mode.setEnabled(not busy)
        self._cancel_button.setEnabled(busy and self._runner is not None)

    # ------------------------------------------------------------ служебное --
    def is_running(self) -> bool:
        """Идёт ли sync в этой вкладке."""
        return self._runner is not None

    def shutdown(self) -> bool:
        """Кооперативная отмена и ожидание при закрытии окна.

        Возвращает ``True``, если поток завершился (или его не было).
        """
        if self._runner is None:
            return True
        self._runner.cancel()
        if self._runner.isRunning():
            return self._runner.wait(5000)
        return True


__all__ = ["SyncTab"]
