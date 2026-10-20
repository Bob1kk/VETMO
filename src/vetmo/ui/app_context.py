"""Точка сборки приложения: Supabase, сервисы, логи.

SQLite/OpenDota в рантайме больше не используются. Reference-данные
(герои, патчи, мета, матчапы) читаются из Supabase; sync-скрипт пишет их
через service_role отдельно от приложения.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from vetmo.data.supabase_heroes import SupabaseHeroRepository
from vetmo.domain.meta_row import MetaRow, PatchInfo
from vetmo.domain.models import Hero
from vetmo.infra.config import Settings
from vetmo.infra.logging import setup_logging
from vetmo.infra.supabase_gateway import SupabaseGateway
from vetmo.services.live_news import LiveNewsService
from vetmo.services.overlay_service import OverlayService
from vetmo.services.supabase_draft import SupabaseDraftService
from vetmo.services.supabase_meta import SupabaseMetaService
from vetmo.services.supabase_settings import SupabaseSettingsService


@dataclass
class AppContext:
    """Контейнер сервисов приложения: всё построено, ничего не запущено."""

    settings: Settings
    gateway: SupabaseGateway
    heroes: SupabaseHeroRepository
    meta: SupabaseMetaService
    settings_service: SupabaseSettingsService
    draft_service: SupabaseDraftService
    news_service: LiveNewsService
    overlay_service: OverlayService
    _hero_ids: list[int] = field(default_factory=list, init=False)

    # --- хелперы доступа к каталогу героев (из worker-потоков) ---
    def hero_count(self) -> int:
        """Количество героев в каталоге."""
        return self.heroes.count()

    def all_heroes(self) -> list[Hero]:
        """Все герои каталога."""
        return self.heroes.get_all()

    def get_hero_by_id(self, hero_id: int) -> Hero | None:
        """Герой по id или None."""
        return self.heroes.get_by_id(hero_id)

    def first_hero_ids(self, limit: int = 10) -> list[int]:
        """Первые limit id героев (совместимость со старым API)."""
        return self.heroes.first_hero_ids(limit)

    def patches(self, limit: int = 30) -> list[PatchInfo]:
        """Патчи для выпадающего списка/поиска."""
        return self.meta.get_patches(limit)

    def meta_report(
        self,
        limit: int = 40,
        rank_tier: int | None = None,
        position: int | None = None,
        patch_id: int | None = None,
    ) -> tuple[list[MetaRow], bool, str | None]:
        """Мета-отчёт из Supabase: (rows, rank_supported, period_text)."""
        try:
            rows = self.meta.get_meta_rows(
                patch_id=patch_id,
                rank_tier=rank_tier,
                position=position,
                limit=limit,
            )
            period = self.meta.get_period()
            return rows, True, period
        except Exception:
            # Пустое состояние UI важнее стектрейса в главном потоке.
            return [], False, None

    def refresh_reference_data(self) -> None:
        """Сбрасывает кэши после ручного обновления/синхронизации."""
        self.heroes.invalidate()
        self.meta.invalidate()


def create_app_context() -> AppContext:
    """Читает настройки, инициализирует логи и сервисы Supabase."""
    settings = Settings()
    setup_logging(settings)
    gateway = SupabaseGateway(settings)
    heroes = SupabaseHeroRepository(gateway)
    meta = SupabaseMetaService(gateway, settings)
    settings_service = SupabaseSettingsService(gateway)
    news_service = LiveNewsService(settings, meta)
    draft_service = SupabaseDraftService(gateway, heroes, settings_service, meta)
    overlay_service = OverlayService(settings_service)  # type: ignore[arg-type]
    return AppContext(
        settings=settings,
        gateway=gateway,
        heroes=heroes,
        meta=meta,
        settings_service=settings_service,
        draft_service=draft_service,
        news_service=news_service,
        overlay_service=overlay_service,
    )


__all__ = ["AppContext", "create_app_context"]
