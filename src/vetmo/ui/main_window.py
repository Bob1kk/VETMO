"""Главное окно лаунчера: новости | мета | настройки + кнопка оверлея (T-010).

Весь SQL/сеть — в services, доступ из worker-потоков QThreadPool;
UI обновляется только из main thread (сигналы Worker).
"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from vetmo import __version__
from vetmo.ui.app_context import AppContext
from vetmo.ui.overlay_window import OverlayWindow
from vetmo.ui.settings_panel import SettingsPanel
from vetmo.ui.theme import theme_for
from vetmo.ui.viewmodels.main_viewmodel import MainViewModel
from vetmo.ui.viewmodels.overlay_vm import OverlaySnapshot, OverlayViewModel
from vetmo.ui.widgets.manual_pick_dialog import ManualPickDialog
from vetmo.ui.widgets.meta_widget import MetaWidget
from vetmo.ui.widgets.news_widget import NewsWidget
from vetmo.ui.widgets.priorities_dialog import PrioritiesDialog
from vetmo.ui.workers import start_worker

_RECS_PER_POSITION = 2
_MATCHUP_HEROES = 10


def _status_label(text: str) -> QLabel:
    """Подпись для статусбара (стили задаёт общая QSS-тема)."""
    label = QLabel(text)
    label.setStyleSheet("padding: 0 8px;")
    return label


class MainWindow(QMainWindow):
    """Лаунчер VETMO: 1100x700, три панели + статусбар + кнопка оверлея."""

    def __init__(self, context: AppContext) -> None:
        super().__init__()
        self._ctx = context
        self._vm = MainViewModel(
            context.news_service,
            context.settings_service,
            context.draft_service,
        )
        self._overlay_vm = OverlayViewModel(
            context.draft_service,
            context.settings_service,
            context.news_service,
            hero_lookup=context.get_hero_by_id,
        )
        self._news_widget = NewsWidget()
        self._meta_widget = MetaWidget()
        self._overlay = OverlayWindow(context.settings_service)
        self._settings_panel = SettingsPanel(
            initial=self._read_settings(), app_version=__version__,
        )
        context.overlay_service.bind_window(lambda: self._overlay)
        self._overlay.refresh_requested.connect(self._refresh_overlay)
        self._vm.news_updated.subscribe(self._news_widget.on_news_updated)
        self._vm.meta_updated.subscribe(self._meta_widget.on_meta_updated)

        self._status_label = _status_label("Готово")
        self._toggle_overlay = QPushButton("Запустить оверлей", self)
        self._toggle_overlay.setObjectName("bigOverlay")
        self._manual_dialog: ManualPickDialog | None = None
        self._priorities_open = False
        self._overlay_visible = False
        self._overlay_busy = False
        self._overlay_pending = False

        self._build_ui()
        self._build_shortcuts()
        self._startup()

    # ---------------------------------------------------------------- UI --
    def _build_ui(self) -> None:
        self.setWindowTitle("VETMO — помощник драфта Dota 2")
        self.resize(1100, 700)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._news_widget)
        splitter.addWidget(self._meta_widget)
        splitter.addWidget(self._settings_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        splitter.setStretchFactor(2, 1)
        self._settings_panel.settings_committed.connect(self._commit_setting)
        self._settings_panel.priorities_requested.connect(
            self._open_priorities)
        self._settings_panel.sync_requested.connect(self._start_sync)

        new_session = QPushButton("Новая сессия драфта", self)
        new_session.setObjectName("secondary")
        new_session.clicked.connect(self._start_draft_session)
        manual = QPushButton("Ручной ввод пика…", self)
        manual.setObjectName("secondary")
        manual.clicked.connect(self._open_manual_pick)
        self._toggle_overlay.clicked.connect(self._toggle_overlay_clicked)

        buttons = QHBoxLayout()
        buttons.addWidget(new_session)
        buttons.addWidget(manual)
        buttons.addStretch(1)
        buttons.addWidget(self._toggle_overlay)

        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        layout.addWidget(splitter, 1)
        layout.addLayout(buttons)
        self.setCentralWidget(central)

        version_label = _status_label(f"vetmo {__version__}")
        self.statusBar().addPermanentWidget(self._status_label)
        self.statusBar().addPermanentWidget(version_label)

    def _build_shortcuts(self) -> None:
        """Esc — скрыть оверлей; Ctrl+Q — выход; F1 — приоритеты позиций."""
        esc = QShortcut(QKeySequence("Esc"), self)
        esc.setContext(Qt.ShortcutContext.WindowShortcut)
        esc.activated.connect(self._hide_overlay)
        quit_short = QShortcut(QKeySequence("Ctrl+Q"), self)
        quit_short.setContext(Qt.ShortcutContext.WindowShortcut)
        quit_short.activated.connect(self.close)
        settings_short = QShortcut(QKeySequence("F1"), self)
        settings_short.setContext(Qt.ShortcutContext.WindowShortcut)
        settings_short.activated.connect(self._open_priorities)

    # ----------------------------------------------------------- startup --
    def _read_settings(self) -> dict:
        """Снимок настроек для панели (записи делает worker, не UI)."""
        service = self._ctx.settings_service
        return {
            "position": service.get_overlay_position(),
            "opacity": service.get_opacity(),
            "theme": service.get_theme(),
            "click_through": service.get_click_through(),
            "show_dire": service.get_show_dire(),
        }

    def _startup(self) -> None:
        """Первичная загрузка: данные в worker; пустой каталог -> авто-синк."""
        self.status("⏳ Загружаем данные…")
        self._load_news()
        self._load_meta()
        start_worker(
            self._ctx.hero_count,
            on_done=self._after_hero_count,
            on_fail=self._default_fail,
        )

    def _after_hero_count(self, count: object) -> None:
        """Каталог пуст -> первая синхронизация в worker (UI не блокируется)."""
        number = count if isinstance(count, int) else 0
        if number == 0:
            self.status("Первый запуск: синхронизируем героев с OpenDota…")
            self._start_sync(120, auto=True)
        else:
            self.status(f"Готово. Героев в базе: {number}")
            self._refresh_overlay()

    # ------------------------------------------------------- data loading --
    def _load_news(self) -> None:
        """Новости: worker -> MainViewModel -> NewsWidget."""
        self._news_widget.set_loading()
        start_worker(
            self._vm.fetch_news,
            on_done=lambda result: self._vm.publish_news(*result),
            on_fail=self._on_news_fail,
        )

    def _on_news_fail(self, message: str) -> None:
        """Ошибка worker'а новостей -> экран ошибки (GUI не падает)."""
        self._news_widget.set_error(message)
        self.status(f"Новости: ошибка ({message})")

    def _load_meta(self) -> None:
        """Мета: worker -> MainViewModel -> MetaWidget."""
        self._meta_widget.set_loading()
        start_worker(
            self._vm.fetch_meta,
            on_done=self._vm.publish_meta,
            on_fail=self._meta_widget.set_error,
        )

    # ------------------------------------------------------------ статус --
    def status(self, text: str) -> None:
        """Сообщение в статусбаре (справа — версия)."""
        self._status_label.setText(text)

    def status_label_text(self) -> str:
        """Текущий текст статуса (для смоука/тестов)."""
        return self._status_label.text()

    def _default_fail(self, message: str) -> None:
        self.status(f"Ошибка: {message}")

    # ------------------------------------------------------------ синхрон --
    def _sync_job(self, limit: int) -> dict:
        """Синхронизация героев + матчапов (первые 10) + Supabase."""
        heroes = self._ctx.opendota.sync_heroes(limit=limit)
        matchups = None
        if heroes.ok:
            ids = self._ctx.first_hero_ids(_MATCHUP_HEROES)
            matchups = self._ctx.opendota.sync_matchups(
                hero_ids=ids, rivals_per_hero=30)
        supabase = self._ctx.supabase.sync_meta_snapshot(limit=50)
        return {"heroes": heroes, "matchups": matchups, "supabase": supabase}

    def _start_sync(self, limit: int = 120, auto: bool = False) -> None:
        """Кнопка «Синхронизировать данные» (или первый запуск)."""
        self._settings_panel.set_sync_enabled(False)
        self.status("⏳ Синхронизация данных OpenDota — зависит от сети…")
        start_worker(
            self._sync_job, limit,
            on_done=lambda result: self._sync_done(result),
            on_fail=self._sync_fail,
        )

    def _sync_done(self, result: dict) -> None:
        """Обновляет все экраны после синхронизации."""
        self._settings_panel.set_sync_enabled(True)
        sent = result["supabase"].get("sent", 0) if result["supabase"] else 0
        cloud = f", Supabase: {sent}" if sent else ""
        self.status(
            f"Синхронизация готова: героев {result['heroes'].ok}"
            f"/{result['heroes'].total}{cloud}")
        self._load_news()
        self._load_meta()
        self._refresh_overlay()

    def _sync_fail(self, message: str) -> None:
        self._settings_panel.set_sync_enabled(True)
        self.status(f"Синхронизация не удалась: {message}")
        self._load_news()
        self._load_meta()

    # ------------------------------------------------------------ оверлей --
    def _toggle_overlay_clicked(self) -> None:
        """FR-003: показать/скрыть оверлей через OverlayService."""
        self._apply_overlay_visibility(not self._overlay_visible)

    def _apply_overlay_visibility(self, visible: bool) -> None:
        self._overlay_visible = visible
        if visible:
            self._ctx.overlay_service.show()
        else:
            self._ctx.overlay_service.hide()
        self._toggle_overlay.setText(
            "Скрыть оверлей" if visible else "Запустить оверлей")

    def _hide_overlay(self) -> None:
        """Esc: скрыть оверлей; кнопка возвращается к «Запустить оверлей»."""
        if self._overlay_visible:
            self._apply_overlay_visibility(False)

    def _refresh_overlay(self) -> None:
        """Пересчёт рекомендаций: worker -> OverlayViewModel -> окно."""
        if self._overlay_busy:
            self._overlay_pending = True
            return
        self._overlay_busy = True

        def job():
            return self._overlay_vm.compute_all(limit=_RECS_PER_POSITION)

        def done(snapshot: OverlaySnapshot) -> None:
            self._overlay_busy = False
            self._overlay.apply_snapshot(snapshot)
            if self._overlay_pending:
                self._overlay_pending = False
                self._refresh_overlay()

        def fail(message: str) -> None:
            self._overlay_busy = False
            self.status(f"Оверлей: ошибка рекомендаций ({message})")

        start_worker(job, on_done=done, on_fail=fail)

    # ------------------------------------------------------------ настройки --
    def _commit_setting(self, kind: str, value) -> None:
        """Панель настроек: запись через SettingsService в worker."""
        def job():
            service = self._ctx.settings_service
            if kind == "position":
                service.set_overlay_position(int(value[0]), int(value[1]))
            elif kind == "opacity":
                service.set_opacity(float(value))
            elif kind == "theme":
                service.set_theme(str(value))
            elif kind == "click_through":
                service.set_click_through(bool(value))
            elif kind == "show_dire":
                service.set_show_dire(bool(value))
            return kind

        def done(done_kind: str) -> None:
            self.status(f"Настройка сохранена: {done_kind}")
            if done_kind == "theme":
                app = QApplication.instance()
                if isinstance(app, QApplication):
                    app.setStyleSheet(theme_for(str(value)))
            if self._overlay_visible:
                self._overlay.apply_settings()
                self._overlay.adjustSize()

        start_worker(job, on_done=done, on_fail=self._default_fail)

    # ------------------------------------------------------------ приоритеты --
    def _open_priorities(self) -> None:
        """F1/кнопка: диалог приоритетов; каталог и профиль — из worker."""
        if self._priorities_open:
            return

        def job():
            heroes = self._ctx.all_heroes()
            priorities = self._ctx.settings_service.get_position_priorities()
            return heroes, priorities

        self._priorities_open = True

        def done(result: tuple) -> None:
            heroes, priorities = result
            if not heroes:
                self.status(
                    "Приоритеты: сначала синхронизируйте каталог героев.")
                self._priorities_open = False
                return
            dialog = PrioritiesDialog(heroes, priorities, self)
            dialog.saved.connect(self._on_priorities_saved)
            dialog.finished.connect(
                lambda _=None: setattr(self, "_priorities_open", False))
            dialog.show()

        def fail(message: str) -> None:
            self._priorities_open = False
            self._default_fail(message)

        start_worker(job, on_done=done, on_fail=fail)

    def _on_priorities_saved(self, priorities: dict) -> None:
        """Запись приоритетов в БД (worker); затем перестройка оверлея."""
        start_worker(
            self._ctx.settings_service.set_position_priorities,
            priorities,
            on_done=lambda _: self.status("Приоритеты позиций сохранены"),
            on_fail=self._default_fail,
        )
        self._vm.notify_priorities_saved(priorities)
        if self._overlay_visible:
            self._refresh_overlay()

    # ------------------------------------------------------------- драфт --
    def _start_draft_session(self) -> None:
        """Новая сессия драфта (шаг 0/10)."""
        start_worker(
            self._ctx.draft_service.start_session,
            on_done=self._after_new_session,
            on_fail=self._default_fail,
        )

    def _after_new_session(self, _state) -> None:
        self.status("Новая сессия драфта начата (шаг 0/10)")
        if self._manual_dialog is not None:
            self._load_manual_state()
        self._refresh_overlay()

    # --------------------------------------------------------- manual pick --
    def _open_manual_pick(self) -> None:
        """T-013: диалог выбора героя (каталог из worker)."""
        if self._manual_dialog is not None:
            self._manual_dialog.raise_()
            self._manual_dialog.show()
            self._load_manual_state()
            return
        start_worker(
            self._ctx.all_heroes,
            on_done=self._manual_dialog_ready,
            on_fail=self._default_fail,
        )

    def _manual_dialog_ready(self, heroes: list) -> None:
        """Создаёт диалог из каталога героев (пустой каталог -> подсказка)."""
        if not heroes:
            self.status(
                "Ручной ввод: каталог пуст — запустите синхронизацию данных.")
            return
        dialog = ManualPickDialog(heroes, self)
        dialog.pick_requested.connect(self._on_pick_requested)
        dialog.finished.connect(
            lambda _=None: setattr(self, "_manual_dialog", None))
        self._manual_dialog = dialog
        self._load_manual_state()
        dialog.show()

    def _load_manual_state(self) -> None:
        """Текущий шаг/команда драфта в открытый диалог."""
        if self._manual_dialog is None:
            return
        start_worker(
            self._vm.fetch_draft_state,
            on_done=self._manual_dialog.show_state,
            on_fail=self._default_fail,
        )

    def _on_pick_requested(self, position, hero_id: int) -> None:
        """Добавляет пик через DraftService.add_pick_auto (worker)."""

        def job():
            return self._ctx.draft_service.add_pick_auto(position, hero_id)

        def done(_state) -> None:
            self.status("Пик записан. Рекомендации обновляются…")
            if self._manual_dialog is not None:
                self._load_manual_state()
            self._refresh_overlay()

        def fail(message: str) -> None:
            if self._manual_dialog is not None:
                self._manual_dialog.on_fail(message)
            self.status(f"Пик не принят: {message}")

        start_worker(job, on_done=done, on_fail=fail)

    # -------------------------------------------------------------- close --
    def closeEvent(self, event) -> None:  # noqa: N802 — Qt API
        """Скрываем оверлей и закрываемся; настройки уже в БД."""
        self._ctx.overlay_service.hide()
        super().closeEvent(event)
