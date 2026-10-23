"""Главное окно VETMO Admin: сайдбар и QStackedWidget с вкладками (T-103)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from vetmo import __version__
from vetmo.admin.tabs import (
    DashboardTab,
    MatchupsTab,
    MetaTab,
    RawTab,
    RunsTab,
    SettingsTab,
    SyncTab,
)
from vetmo.admin.tabs.common import SyncState
from vetmo.ui.theme import theme_for

if TYPE_CHECKING:
    from vetmo.admin.context import AdminContext

_SECTIONS: tuple[str, ...] = (
    "Обзор",
    "Синхронизация",
    "Мета",
    "Матчапы",
    "Сырые данные",
    "История",
    "Настройки",
)


class AdminWindow(QMainWindow):
    """Окно Admin: слева разделы, справа соответствующая вкладка."""

    def __init__(self, context: AdminContext) -> None:
        super().__init__()
        self._ctx = context
        self._sync_state = SyncState(self)
        self.setWindowTitle("VETMO Admin — обновление данных Dota 2")
        self.setMinimumSize(1180, 720)
        self.resize(1360, 880)
        self.setStyleSheet(theme_for("dark"))
        self._build_ui()
        self._status_bar = self.statusBar()
        self._status_bar.showMessage("Готово")
        version = QLabel(f"VETMO Admin {__version__}", self)
        version.setObjectName("mutedSmall")
        self._status_bar.addPermanentWidget(version)

    # ---------------------------------------------------------------- UI --
    def _build_ui(self) -> None:
        self._nav = QListWidget(self)
        self._nav.setObjectName("adminNav")
        self._nav.setFixedWidth(210)
        self._nav.setSpacing(2)
        self._nav.addItems(list(_SECTIONS))
        self._nav.setCurrentRow(0)

        brand = QLabel("VETMO", self)
        brand.setObjectName("brandTitle")
        brand_sub = QLabel("ADMIN · ОБНОВЛЕНИЕ БД", self)
        brand_sub.setObjectName("brandSubtitle")

        sidebar = QWidget(self)
        sidebar.setFixedWidth(230)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(8)
        sidebar_layout.addWidget(brand)
        sidebar_layout.addWidget(brand_sub)
        sidebar_layout.addWidget(self._nav, 1)

        self._stack = QStackedWidget(self)
        self._dashboard = DashboardTab(context=self._ctx, sync_state=self._sync_state)
        self._sync_tab = SyncTab(context=self._ctx, sync_state=self._sync_state)
        self._meta_tab = MetaTab(self._ctx)
        self._matchups_tab = MatchupsTab(self._ctx)
        self._raw_tab = RawTab(self._ctx)
        self._runs_tab = RunsTab(self._ctx)
        self._settings_tab = SettingsTab(self._ctx)
        self._tabs = (
            self._dashboard,
            self._sync_tab,
            self._meta_tab,
            self._matchups_tab,
            self._raw_tab,
            self._runs_tab,
            self._settings_tab,
        )
        for tab in self._tabs:
            self._stack.addWidget(tab)
            tab.status_message.connect(self._show_status)

        central = QWidget(self)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(12, 12, 12, 8)
        layout.setSpacing(12)
        layout.addWidget(sidebar)
        layout.addWidget(self._stack, 1)
        self.setCentralWidget(central)

        self._nav.currentRowChanged.connect(self._stack.setCurrentIndex)
        self._nav.currentRowChanged.connect(self._on_section_changed)

    def _on_section_changed(self, index: int) -> None:
        if 0 <= index < len(_SECTIONS):
            self._show_status(f"Раздел: {_SECTIONS[index]}")

    def _show_status(self, message: str) -> None:
        self._status_bar.showMessage(str(message))

    # ------------------------------------------------------------ API для тестов --
    def tab_titles(self) -> list[str]:
        """Названия разделов сайдбара."""
        return [self._nav.item(i).text() for i in range(self._nav.count())]

    def select_tab(self, index: int) -> None:
        """Переключает раздел по индексу (для смоук-тестов)."""
        if 0 <= index < self._nav.count():
            self._nav.setCurrentRow(index)

    def current_tab_index(self) -> int:
        """Индекс текущего раздела."""
        return self._stack.currentIndex()

    def status_text(self) -> str:
        """Текущее сообщение статусбара."""
        return self._status_bar.currentMessage()

    # -------------------------------------------------------------- close --
    def closeEvent(self, event) -> None:  # noqa: N802 — Qt API
        """Останавливает активный sync и закрывает окно."""
        busy = self._sync_tab.is_running() or self._dashboard.running_mode() is not None
        if busy:
            answer = QMessageBox.question(
                self,
                "Синхронизация выполняется",
                "Sync ещё не завершён. Отменить и закрыть VETMO Admin?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        stopped = self._dashboard.shutdown()
        stopped = self._sync_tab.shutdown() and stopped
        if not stopped:
            QMessageBox.warning(
                self,
                "Синхронизация не завершена",
                "Не удалось остановить sync за 5 секунд. Окно останется открытым.",
            )
            event.ignore()
            return
        for tab in self._tabs:
            if tab not in (self._dashboard, self._sync_tab):
                tab.shutdown()
        super().closeEvent(event)


__all__ = ["AdminWindow"]
