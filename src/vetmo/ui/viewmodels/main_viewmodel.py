"""MainViewModel: данные для лаунчера (новости/мета/настройки). Без Qt (NFR-005).

UI (MainWindow) запускает fetch_* в QThreadPool-воркере и публикует
результат через publish_* — подписчики (виджеты) получают колбэком.
"""

from vetmo.services.draft_service import DraftService
from vetmo.services.news_service import MetaSummary, NewsItem, NewsService
from vetmo.services.settings_service import SettingsService
from vetmo.ui.viewmodels.callbacks import CallbackList


class MainViewModel:
    """Состояние лаунчера: новости, мета, приоритеты позиций."""

    def __init__(
        self,
        news_service: NewsService,
        settings_service: SettingsService,
        draft_service: DraftService,
    ) -> None:
        self._news = news_service
        self._settings = settings_service
        self._draft = draft_service

        self.news_updated = CallbackList()      # (list[NewsItem], is_online)
        self.meta_updated = CallbackList()      # (MetaSummary,)
        self.priorities_updated = CallbackList()  # (dict[int, list[int]],)
        self.draft_updated = CallbackList()     # (DraftSession,)

    # --- запросы данных (worker-поток) ---
    def fetch_news(self, limit: int = 5) -> tuple[list[NewsItem], bool]:
        """Новости патчей + статус сети (offline fallback из БД внутри сервиса)."""
        return self._news.get_latest_patch_news(limit)

    def fetch_meta(self, limit: int = 10) -> MetaSummary:
        """Мета-сводка: версия патча и топ героев."""
        return self._news.get_meta_summary(limit)

    def fetch_draft_state(self):
        """Состояние последней сессии драфта (авто-создание внутри сервиса)."""
        return self._draft.get_state()

    # --- публикация результата (UI-поток) ---
    def publish_news(self, items: list[NewsItem], is_online: bool) -> None:
        """Рассылает новости подписчикам."""
        self.news_updated.emit(items, is_online)

    def publish_meta(self, summary: MetaSummary) -> None:
        """Рассылает мета-сводку подписчикам."""
        self.meta_updated.emit(summary)

    def publish_draft_state(self, state) -> None:
        """Рассылает состояние драфта подписчикам."""
        self.draft_updated.emit(state)

    # --- настройки приоритетов (дефолт для диалога) ---
    def get_priorities(self) -> dict[int, list[int]]:
        """Текущие приоритеты позиций 1..5 -> hero_id."""
        return self._settings.get_position_priorities()

    def notify_priorities_saved(self, priorities: dict[int, list[int]]) -> None:
        """Сообщает о сохранённых приоритетах (запись БД делает UI-воркер)."""
        self.priorities_updated.emit(priorities)
