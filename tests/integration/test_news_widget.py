"""Регрессии NewsWidget: обновления не накапливают строки и stretch."""

from vetmo.services.news_service import NewsItem
from vetmo.ui.widgets.news_widget import NewsWidget


def _items(count: int) -> list[NewsItem]:
    """N новостей с уникальными ссылками."""
    return [
        NewsItem(title=f"Новость {i}", body="текст", url=f"https://e.test/{i}")
        for i in range(count)
    ]


def test_repeated_set_news_does_not_accumulate_layout(qtbot) -> None:
    """Повторный set_news заменяет строки, а не добавляет новые поверх."""
    widget = NewsWidget()
    qtbot.addWidget(widget)

    widget.set_news(_items(2), True)
    assert widget.row_count() == 2
    assert widget._rows_layout.count() == 3  # 2 строки + stretch

    widget.set_news(_items(3), True)
    assert widget.row_count() == 3
    assert widget._rows_layout.count() == 4  # 3 строки + stretch, не 6

    widget.set_loading()
    assert widget.row_count() == 0
    assert widget._rows_layout.count() == 0
