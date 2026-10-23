"""Интеграционные тесты MainWindow (T-010/US-001/FR-001/FR-003, T-018).

Сеть полностью заглушена в фикстуре app_env (conftest.py): авто-синк на
пустой БД не лезет в интернет, окно строится автономно на tmp-SQLite.
"""

from PySide6.QtWidgets import QPushButton

from vetmo.ui.main_window import MainWindow

OVERLAY_ON = "Запустить оверлей"
OVERLAY_OFF = "Скрыть оверлей"


def test_main_window_created_and_shown_under_3s(make_window) -> None:
    """NFR-001: окно создаётся и показывается быстрее 3 секунд."""
    window = make_window()
    assert isinstance(window, MainWindow)
    assert window.isVisible()
    seconds = getattr(window, "_build_seconds", 999.0)
    assert seconds < 3.0, f"MainWindow строится слишком долго: {seconds:.2f} c"


def test_main_window_shows_news_panel(make_window, qtbot) -> None:
    """FR-001 (матрица трассировки): панели новостей и меты присутствуют."""
    window = make_window()
    news = window._news_widget
    meta = window._meta_widget
    assert news is not None and news.parent() is not None
    assert meta is not None and meta.parent() is not None
    assert news.isVisibleTo(window)
    assert meta.isVisibleTo(window)
    # панель новостей отработала (заглушка вернула ([], True)).
    qtbot.waitUntil(
        lambda: "Новостей пока нет" in news._placeholder.text(),
        timeout=10000,
    )
    assert news.row_count() == 0
    assert "Новостей пока нет" in news._placeholder.text()


def test_overlay_button_found_by_text(make_window) -> None:
    """Есть QQPushButton с текстом «Запустить оверлей» — ищем по findChildren."""
    window = make_window()
    buttons = window.findChildren(QPushButton)
    texts = [b.text() for b in buttons]
    assert any(OVERLAY_ON in t for t in texts), texts
    # whitebox-соответствие: кнопка оверлея помечена objectName
    assert window._toggle_overlay.objectName() == "bigOverlay"


def test_toggle_overlay_switches_button_text_and_visibility(
    make_window,
) -> None:
    """FR-003 (матрица): toggle переключает статус-текст «Запустить↔Скрыть»."""
    window = make_window()
    button = window._toggle_overlay
    assert button.text() == OVERLAY_ON
    assert not window._overlay.isVisible()

    window._toggle_overlay_clicked()
    assert button.text() == OVERLAY_OFF
    assert window._overlay.isVisible()

    window._toggle_overlay_clicked()
    assert button.text() == OVERLAY_ON
    assert not window._overlay.isVisible()


def test_esc_hides_overlay_and_restores_button(make_window) -> None:
    """Esc-шорткат: скрытие оверлея возвращает кнопку к «Запустить оверлей»."""
    window = make_window()
    window._toggle_overlay_clicked()
    assert window._toggle_overlay.text() == OVERLAY_OFF
    window._hide_overlay()
    assert window._toggle_overlay.text() == OVERLAY_ON


def test_startup_workers_complete_without_crash(
    make_window, qtbot
) -> None:
    """Авто-пуск на пустом каталоге: воркеры завершаются, статус показывает размер каталога.

    Сеть заглушена, каталог из seed-фолбэка (127 героев).
    """
    window = make_window()
    qtbot.waitUntil(
        lambda: window.status_label_text().startswith("Готово. Героев в каталоге:"),
        timeout=10000,
    )
    assert "127" in window.status_label_text()


def test_overlay_gear_opens_settings_tab(make_window) -> None:
    """Gear оверлея открывает существующую вкладку настроек, не дублирует её."""
    window = make_window()
    assert window._sidebar_tabs.currentWidget() is window._news_widget

    window._overlay.settings_requested.emit()
    assert window._sidebar_tabs.currentWidget() is window._settings_panel


def test_overlay_gear_hides_always_on_top_overlay(make_window) -> None:
    """Always-on-top оверлей не перекрывает панель настроек после gear."""
    window = make_window()
    window._toggle_overlay_clicked()
    assert window._overlay.isVisible()

    window._overlay.settings_requested.emit()
    assert not window._overlay.isVisible()
    assert window._sidebar_tabs.currentWidget() is window._settings_panel
    assert window._toggle_overlay.text() == OVERLAY_ON


def test_settings_panel_describes_supabase_state(make_window) -> None:
    """Панель данных честно показывает, настроен ли Supabase."""
    window = make_window()
    assert window._settings_panel._supabase_note.text().startswith("Supabase:")
