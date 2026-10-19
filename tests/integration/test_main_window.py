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
    """FR-001 (матрица трассировки): панель новостей присутствует в окне."""
    window = make_window()
    news = window._news_widget
    meta = window._meta_widget
    assert news is not None and news.parent() is not None
    assert meta is not None and meta.parent() is not None
    assert news.isVisibleTo(window)
    assert meta.isVisibleTo(window)
    # воркер новостей отработал, список заполнен (заглушка вернула []).
    qtbot.waitUntil(
        lambda: (
            news._list.count() > 0
            and "Ошибка" not in news._list.item(0).text()
            and "Загрузка" not in news._list.item(0).text()
        ),
        timeout=10000,
    )
    assert "Новостей пока нет" in news._list.item(0).text()
    assert "Онлайн" == news._badge.text()  # заглушка возвращает is_online=True


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
    """Авто-синк на пустой БД: воркеры завершаются, статус «Синхронизация готова».

    Сеть заглушена (SyncResult(total=0, ok=0)), поэтому счёт 0/0.
    """
    window = make_window()
    qtbot.waitUntil(
        lambda: window.status_label_text().startswith("Синхронизация готова"),
        timeout=10000,
    )
    assert "героев 0/0" in window.status_label_text()
