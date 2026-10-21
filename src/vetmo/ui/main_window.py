"""Главное окно лаунчера: новости | мета | настройки + кнопка оверлея (T-010).

Весь SQL/сеть — в services, доступ из worker-потоков QThreadPool;
UI обновляется только из main thread (сигналы Worker).
"""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from vetmo import __version__
from vetmo.ui.app_context import AppContext
from vetmo.ui.app_icon import rounded_brand_pixmap
from vetmo.ui.monitor import move_launcher_to_screen, resolve_screen
from vetmo.ui.overlay_window import OverlayWindow
from vetmo.ui.settings_panel import SettingsPanel
from vetmo.ui.theme import theme_for
from vetmo.ui.viewmodels.main_viewmodel import MainViewModel
from vetmo.ui.viewmodels.overlay_vm import OverlaySnapshot, OverlayViewModel
from vetmo.ui.widgets.manual_pick_dialog import ManualPickDialog
from vetmo.ui.widgets.meta_report import MetaReportWidget
from vetmo.ui.widgets.news_widget import NewsWidget
from vetmo.ui.widgets.priorities_dialog import PrioritiesDialog
from vetmo.ui.workers import start_worker

_RECS_PER_POSITION = 2


_NEWS_REFRESH_MS = 60 * 60 * 1000  # новости по таймеру: раз в час (R2, задача C)
_META_ROWS_LIMIT = 200  # весь каталог Dota 2 (127 героев) + запас


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
            context.news_service,  # type: ignore[arg-type]
            context.settings_service,  # type: ignore[arg-type]
            context.draft_service,  # type: ignore[arg-type]
            meta_report_loader=getattr(context, "meta_report", None),
        )
        self._overlay_vm = OverlayViewModel(
            context.draft_service,  # type: ignore[arg-type]
            context.settings_service,  # type: ignore[arg-type]
            context.news_service,  # type: ignore[arg-type]
            hero_lookup=context.get_hero_by_id,
        )
        self._news_widget = NewsWidget()
        self._meta_widget = MetaReportWidget()
        self._overlay = OverlayWindow(context.settings_service)  # type: ignore[arg-type]
        self._settings_panel = SettingsPanel(
            initial=self._read_settings(), app_version=__version__,
        )
        self._settings_panel.set_supabase_note(
            bool(context.settings.supabase_url
                 and context.settings.supabase_publishable_key)
        )
        context.overlay_service.bind_window(lambda: self._overlay)
        self._overlay.refresh_requested.connect(self._refresh_overlay)
        self._overlay.settings_requested.connect(self._open_overlay_settings)
        self._overlay.set_matchup_loader(self._matchup_loader)
        self._meta_widget.set_matchup_loader(self._matchup_loader)
        self._meta_widget.set_matchup_details_loader(
            self._matchup_details_loader)
        self._vm.news_updated.subscribe(self._news_widget.on_news_updated)
        self._vm.meta_updated.subscribe(self._meta_widget.on_meta_report)
        self._meta_widget.filters_changed.connect(self._load_meta)
        self._news_timer = QTimer(self)
        self._news_timer.setInterval(_NEWS_REFRESH_MS)
        self._news_timer.timeout.connect(self._load_news)

        self._status_label = _status_label("Готово")
        self._toggle_overlay = QPushButton("Запустить оверлей", self)
        self._toggle_overlay.setObjectName("bigOverlay")
        self._manual_dialog: ManualPickDialog | None = None
        self._priorities_open = False
        self._overlay_visible = False
        self._overlay_busy = False
        self._overlay_pending = False
        self._sync_busy = False

        self._build_ui()
        self._build_shortcuts()
        self._apply_launcher_screen()
        self._startup()

    # ---------------------------------------------------------------- UI --
    def _build_ui(self) -> None:
        self.setWindowTitle("VETMO — помощник драфта Dota 2")
        self.setMinimumSize(1180, 700)
        self.resize(1280, 800)

        self._settings_panel.settings_committed.connect(self._commit_setting)
        self._settings_panel.priorities_requested.connect(
            self._open_priorities)
        self._settings_panel.sync_requested.connect(self._start_sync)
        self._settings_panel.overlay_toggle_requested.connect(
            self._toggle_overlay_clicked)

        new_session = QPushButton("Новая сессия", self)
        new_session.setObjectName("headerGhost")
        new_session.setToolTip("Начать драфт с шага 0/10")
        new_session.clicked.connect(self._start_draft_session)
        refresh_db = QPushButton("Обновить из БД", self)
        refresh_db.setObjectName("headerGhost")
        refresh_db.setToolTip(
            "Перечитать мету, патчи и новости из Supabase. Только чтение — "
            "запись выполняет VETMO Admin.")
        refresh_db.clicked.connect(self._refresh_from_db)
        self._refresh_db_button = refresh_db
        manual = QPushButton("Ручной пик…", self)
        manual.setObjectName("headerGhost")
        manual.setToolTip("Записать пик вручную")
        manual.clicked.connect(self._open_manual_pick)
        self._toggle_overlay.clicked.connect(self._toggle_overlay_clicked)

        header = QFrame(self)
        header.setObjectName("appHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 8, 12, 8)
        header_layout.setSpacing(10)
        mark = QLabel(header)
        mark.setObjectName("brandMark")
        mark.setFixedSize(40, 40)
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand_pixmap = rounded_brand_pixmap(40)
        if brand_pixmap.isNull():
            mark.setText("V")
        else:
            mark.setPixmap(brand_pixmap)
        title_box = QVBoxLayout()
        title_box.setSpacing(0)
        brand = QLabel("VETMO", header)
        brand.setObjectName("brandTitle")
        subtitle = QLabel("DOTA 2 DRAFT INTELLIGENCE", header)
        subtitle.setObjectName("brandSubtitle")
        title_box.addWidget(brand)
        title_box.addWidget(subtitle)
        header_layout.addWidget(mark)
        header_layout.addLayout(title_box)
        header_layout.addStretch(1)
        header_layout.addWidget(refresh_db)
        header_layout.addWidget(new_session)
        header_layout.addWidget(manual)
        header_layout.addWidget(self._toggle_overlay)

        self._sidebar_tabs = QTabWidget(self)
        self._sidebar_tabs.setObjectName("sidebarTabs")
        self._sidebar_tabs.setMinimumWidth(320)
        self._sidebar_tabs.setMaximumWidth(368)
        self._sidebar_tabs.addTab(self._news_widget, "НОВОСТИ")
        self._sidebar_tabs.addTab(self._settings_panel, "НАСТРОЙКИ")
        self._sidebar_tabs.setCurrentIndex(0)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(10)
        body.addWidget(self._sidebar_tabs)
        body.addWidget(self._meta_widget, 1)

        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(14, 12, 14, 10)
        layout.setSpacing(10)
        layout.addWidget(header)
        layout.addLayout(body, 1)
        self.setCentralWidget(central)

        self.statusBar().addWidget(self._status_label, 1)

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
        overlay_settings = QShortcut(QKeySequence("Ctrl+,"), self)
        overlay_settings.setContext(Qt.ShortcutContext.WindowShortcut)
        overlay_settings.activated.connect(self._open_overlay_settings)
        refresh_db = QShortcut(QKeySequence("Ctrl+R"), self)
        refresh_db.setContext(Qt.ShortcutContext.WindowShortcut)
        refresh_db.activated.connect(self._refresh_from_db)

    def _apply_launcher_screen(self) -> None:
        """Открывает лаунчер на выбранном мониторе (по умолчанию второй)."""
        try:
            index = self._ctx.settings_service.get_monitor_index()
            move_launcher_to_screen(self, resolve_screen(index))
        except Exception:  # noqa: BLE001 - монитор не критичен для запуска
            pass

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
            "monitor": service.get_monitor_index(),
        }

    def _startup(self) -> None:
        """Первичная загрузка: Supabase читается в worker, UI не блокируется."""
        self.status("Загружаем данные из Supabase…")
        self._load_news()
        self._load_meta()
        self._news_timer.start()
        start_worker(
            self._ctx.hero_count,
            on_done=self._after_hero_count,
            on_fail=self._default_fail,
        )

    def _after_hero_count(self, count: object) -> None:
        """Показывает размер каталога; пустой каталог — подсказка про seed."""
        number = count if isinstance(count, int) else 0
        if number == 0:
            self.status(
                "Каталог героев пуст: примените миграцию и seed Supabase.")
        else:
            self.status(f"Готово. Героев в каталоге: {number}")
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
        """Мета-отчёт с фильтрами: worker -> MainViewModel -> MetaReportWidget."""
        self._meta_widget.set_loading()
        position, rank_tier = self._meta_widget.filters()
        start_worker(
            self._vm.fetch_meta_report,
            _META_ROWS_LIMIT, rank_tier, position,
            on_done=self._vm.publish_meta_report,
            on_fail=self._meta_widget.set_error,
        )

    def _matchup_loader(self, hero_id: int) -> tuple | None:
        """Тултип контрпиков: контракт DraftService (api-агент), лениво."""
        getter = getattr(self._ctx.draft_service, "get_matchup_tooltip", None)
        if getter is None:
            return None
        return getter(hero_id)

    def _matchup_details_loader(
        self, hero_id: int, rank_tier: int, patch_id: int | None,
    ):
        """Диалог матчапов: три десятки по выбранному ранговому срезу."""
        getter = getattr(self._ctx.draft_service, "get_matchup_report", None)
        if getter is None:
            raise RuntimeError("Сервис матчапов недоступен")
        return getter(hero_id, rank_tier, patch_id)

    # ------------------------------------------------------------ статус --
    def status(self, text: str) -> None:
        """Сообщение в статусбаре (справа — версия)."""
        self._status_label.setText(text)

    def status_label_text(self) -> str:
        """Текущий текст статуса (для смоука/тестов)."""
        return self._status_label.text()

    def _default_fail(self, message: str) -> None:
        self.status(f"Ошибка: {message}")

    # ------------------------------------------------------------ обновление --
    def _refresh_from_db(self) -> None:
        """Кнопка «Обновить из БД»: только чтение Supabase (T-111)."""
        if self._sync_busy:
            self.status("Обновление из БД уже выполняется…")
            return
        self.status("Перечитываем данные из Supabase (только чтение)…")
        self._start_sync()

    def _start_sync(self, limit: int = 0, auto: bool = False) -> None:
        """«Обновить данные»: сбросить кэши и перечитать Supabase.

        Reference-данные пишет отдельный sync-скрипт с service_role; приложение
        никогда не выполняет DDL/запись меты.
        """
        if self._sync_busy:
            return
        self._sync_busy = True
        self._settings_panel.set_sync_enabled(False)
        self._refresh_db_button.setEnabled(False)
        self.status("Перечитываем данные из Supabase…")

        def job() -> int:
            self._ctx.refresh_reference_data()
            return self._ctx.hero_count()

        start_worker(job, on_done=self._sync_done, on_fail=self._sync_fail)

    def _sync_done(self, count: object) -> None:
        """Обновляет все экраны после перечитывания Supabase."""
        self._sync_busy = False
        self._settings_panel.set_sync_enabled(True)
        self._refresh_db_button.setEnabled(True)
        number = count if isinstance(count, int) else 0
        self.status(f"Данные Supabase обновлены. Героев: {number}")
        self._load_news()
        self._load_meta()
        self._refresh_overlay()

    def _sync_fail(self, message: str) -> None:
        self._sync_busy = False
        self._settings_panel.set_sync_enabled(True)
        self._refresh_db_button.setEnabled(True)
        self.status(f"Не удалось перечитать Supabase: {message}")
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
        self._settings_panel.set_overlay_visible(visible)

    def _hide_overlay(self) -> None:
        """Esc: скрыть оверлей; кнопка возвращается к «Запустить оверлей»."""
        if self._overlay_visible:
            self._apply_overlay_visibility(False)

    def _open_overlay_settings(self) -> None:
        """Gear из оверлея / Ctrl+, — открыть вкладку настроек лаунчера.

        Оверлей поверх всех перекрыл бы панель настроек на экране, поэтому
        на время конфигурации он скрывается; вернуть — кнопкой «Показать
        оверлей» (в шапке или настройках).
        """
        if self._overlay_visible:
            self._apply_overlay_visibility(False)
        self._sidebar_tabs.setCurrentWidget(self._settings_panel)
        if self.isMinimized():
            self.showNormal()
        self.show()
        self.raise_()
        self.activateWindow()
        self.status("Настройки оверлея — изменения сохраняются сразу")

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
            elif kind == "monitor":
                service.set_monitor_index(int(value))
            return kind

        def done(done_kind: str) -> None:
            self.status(f"Настройка сохранена: {done_kind}")
            if done_kind == "theme":
                app = QApplication.instance()
                if isinstance(app, QApplication):
                    app.setStyleSheet(theme_for(str(value)))
            if done_kind == "monitor":
                self._apply_launcher_screen()
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
                    "Приоритеты: сначала обновите каталог героев.")
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
        def done(_: object) -> None:
            self.status("Приоритеты позиций сохранены")
            self._vm.notify_priorities_saved(priorities)
            if self._overlay_visible:
                # Refresh только после коммита: иначе воркер прочитает старые
                # приоритеты из БД (гонка записи и чтения).
                self._refresh_overlay()

        start_worker(
            self._ctx.settings_service.set_position_priorities,
            priorities,
            on_done=done,
            on_fail=self._default_fail,
        )

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
                "Ручной ввод: каталог пуст — обновите данные в настройках.")
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
