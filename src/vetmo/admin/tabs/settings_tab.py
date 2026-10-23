"""Вкладка «Настройки»: пути, флаги ключей и проверки подключений (T-110).

Значения секретов никогда не отображаются: только флаги «задан/не задан».
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from vetmo.admin.tabs.common import as_int, format_datetime, status_text
from vetmo.ui.workers import start_worker

if TYPE_CHECKING:
    from vetmo.admin.context import AdminContext

_OK_STYLE = "color: #43C59E;"
_BAD_STYLE = "color: #E35D6A;"


class SettingsTab(QWidget):
    """Диагностика окружения Admin: secrets.env, Supabase и STRATZ."""

    status_message = Signal(str)

    def __init__(self, context: AdminContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = context
        self._build_ui()

    # ---------------------------------------------------------------- UI --
    def _build_ui(self) -> None:
        title = QLabel("Настройки", self)
        title.setObjectName("h1")
        subtitle = QLabel(
            "Значения ключей здесь не показываются — только признаки наличия. "
            "Секреты хранятся вне репозитория и exe.",
            self,
        )
        subtitle.setObjectName("muted")
        subtitle.setWordWrap(True)

        secrets_path = self._secrets_path()
        sync = getattr(self._ctx, "sync", None)
        supabase_url = str(getattr(sync, "supabase_url", "") or "")
        stratz_url = str(getattr(sync, "stratz_api_url", "") or "")

        secrets_form = QFormLayout()
        secrets_form.setHorizontalSpacing(12)
        secrets_form.setVerticalSpacing(6)
        self._path_label = QLabel(str(secrets_path), self)
        self._path_label.setWordWrap(True)
        self._path_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self._file_label = QLabel(self)
        exists = secrets_path.is_file()
        self._file_label.setText("файл найден" if exists else "файл не найден")
        self._file_label.setStyleSheet(_OK_STYLE if exists else _BAD_STYLE)
        secrets_form.addRow("Файл секретов:", self._path_label)
        secrets_form.addRow("Статус файла:", self._file_label)
        secrets_form.addRow(
            "service_role:",
            self._flag_label(bool(getattr(sync, "service_key", ""))),
        )
        secrets_form.addRow(
            "STRATZ token:",
            self._flag_label(bool(getattr(sync, "stratz_token", ""))),
        )
        secrets_form.addRow(
            "Supabase URL:",
            self._flag_label(bool(supabase_url)),
        )

        connections_form = QFormLayout()
        connections_form.setHorizontalSpacing(12)
        connections_form.setVerticalSpacing(6)
        supabase_label = QLabel(supabase_url or "не задан", self)
        supabase_label.setWordWrap(True)
        supabase_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        stratz_label = QLabel(stratz_url or "не задан", self)
        stratz_label.setWordWrap(True)
        stratz_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        connections_form.addRow("Supabase URL:", supabase_label)
        connections_form.addRow("STRATZ URL:", stratz_label)

        self._supabase_button = QPushButton("Проверить Supabase", self)
        self._supabase_button.setObjectName("secondary")
        self._supabase_button.clicked.connect(self._check_supabase)
        self._stratz_button = QPushButton("Проверить STRATZ", self)
        self._stratz_button.setObjectName("secondary")
        self._stratz_button.clicked.connect(self._check_stratz)
        self._folder_button = QPushButton("Открыть папку с секретами", self)
        self._folder_button.setObjectName("secondary")
        self._folder_button.clicked.connect(self._open_secrets_folder)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        buttons.addWidget(self._supabase_button)
        buttons.addWidget(self._stratz_button)
        buttons.addWidget(self._folder_button)
        buttons.addStretch(1)

        self._result = QLabel("Проверки ещё не выполнялись", self)
        self._result.setObjectName("stateInfo")
        self._result.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(self._section("СЕКРЕТЫ"))
        layout.addLayout(secrets_form)
        layout.addWidget(self._section("ПОДКЛЮЧЕНИЯ"))
        layout.addLayout(connections_form)
        layout.addWidget(self._section("ПРОВЕРКИ"))
        layout.addLayout(buttons)
        layout.addWidget(self._result)
        layout.addStretch(1)

    @staticmethod
    def _section(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("sectionTitle")
        return label

    @staticmethod
    def _flag_label(present: bool) -> QLabel:
        label = QLabel("задан" if present else "не задан")
        label.setStyleSheet(_OK_STYLE if present else _BAD_STYLE)
        return label

    def _secrets_path(self) -> Path:
        path = getattr(self._ctx, "secrets_path", None)
        if isinstance(path, Path):
            return path
        return Path(str(path or "secrets.env"))

    # ------------------------------------------------------------ проверки --
    def _set_result(self, text: str, *, ok: bool) -> None:
        self._result.setText(text)
        self._result.setStyleSheet(_OK_STYLE if ok else _BAD_STYLE)
        self.status_message.emit(text)

    def _check_supabase(self) -> None:
        self._supabase_button.setEnabled(False)
        self._set_result("Supabase: проверяем подключение…", ok=True)

        def done(run: dict[str, Any] | None) -> None:
            self._supabase_button.setEnabled(True)
            if not run:
                self._set_result(
                    "Supabase: подключение работает, запусков sync пока нет.",
                    ok=True,
                )
                return
            self._set_result(
                "Supabase: подключение работает. "
                f"Последний запуск #{run.get('id', '—')}: "
                f"{status_text(run.get('status'))} "
                f"({format_datetime(run.get('started_at'))}).",
                ok=True,
            )

        def fail(message: str) -> None:
            self._supabase_button.setEnabled(True)
            self._set_result(f"Supabase: ошибка — {message}", ok=False)

        start_worker(self._ctx.repository.last_run, on_done=done, on_fail=fail)

    def _check_stratz(self) -> None:
        self._stratz_button.setEnabled(False)
        self._set_result("STRATZ: проверяем подключение…", ok=True)

        def done(versions: list[dict[str, Any]]) -> None:
            self._stratz_button.setEnabled(True)
            latest = ""
            if versions:
                newest = max(
                    versions,
                    key=lambda row: as_int(row.get("id"), 0) or 0,
                )
                latest = str(newest.get("name") or newest.get("id") or "")
            suffix = f", последний патч: {latest}" if latest else ""
            self._set_result(
                f"STRATZ: подключение работает, патчей: {len(versions)}{suffix}.",
                ok=True,
            )

        def fail(message: str) -> None:
            self._stratz_button.setEnabled(True)
            self._set_result(f"STRATZ: ошибка — {message}", ok=False)

        start_worker(self._ctx.client.game_versions, on_done=done, on_fail=fail)

    def _open_secrets_folder(self) -> None:
        path = self._secrets_path()
        folder = path.parent
        if not folder.is_dir():
            QMessageBox.warning(
                self,
                "Папка не найдена",
                f"Папка с секретами не существует:\n{folder}\n\n"
                "Создайте secrets.env с ключами VETMO_SYNC_*.",
            )
            self.status_message.emit("Папка с секретами не найдена")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
        self._set_result(f"Открыта папка: {folder}", ok=True)

    # ------------------------------------------------------------ служебное --
    def result_text(self) -> str:
        """Текст результата последней проверки (для смоук-тестов)."""
        return self._result.text()

    def shutdown(self) -> None:
        """Проверки идут через QThreadPool; отменять нечего."""


__all__ = ["SettingsTab"]
