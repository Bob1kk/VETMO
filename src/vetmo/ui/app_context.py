"""Точка сборки приложения: настройки, БД, логи, сервисы (композиция).

Используется из main.py и смоук-скриптов; никаких импортов Qt.
"""

from dataclasses import dataclass, field

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from vetmo.data.db import create_db, migrate
from vetmo.data.repositories.hero_repo import HeroRepository
from vetmo.data.repositories.meta_repo import MetaRepository
from vetmo.domain.models import Hero
from vetmo.infra.config import Settings
from vetmo.infra.logging import setup_logging
from vetmo.infra.supabase_stub import SupabaseClient
from vetmo.services.draft_service import DraftService
from vetmo.services.news_service import NewsService
from vetmo.services.opendota_client import OpenDotaClient
from vetmo.services.overlay_service import OverlayService
from vetmo.services.settings_service import SettingsService
from vetmo.services.validator_service import ValidatorService


@dataclass
class AppContext:
    """Контейнер сервисов приложения: всё построено, ничего не запущено."""

    settings: Settings
    engine: Engine
    sessionmaker: sessionmaker[Session]
    settings_service: SettingsService
    draft_service: DraftService
    news_service: NewsService
    opendota: OpenDotaClient
    supabase: SupabaseClient
    overlay_service: OverlayService
    _hero_ids: list[int] = field(default_factory=list, init=False)

    # --- хелперы доступа к каталогу героев (вызываются из worker-потоков) ---
    def hero_count(self) -> int:
        """Количество героев в БД."""
        with self.sessionmaker() as session:
            return HeroRepository(session).count()

    def all_heroes(self) -> list[Hero]:
        """Все герои каталога."""
        with self.sessionmaker() as session:
            return HeroRepository(session).get_all()

    def get_hero_by_id(self, hero_id: int) -> Hero | None:
        """Герой по id или None."""
        with self.sessionmaker() as session:
            return HeroRepository(session).get_by_id(hero_id)

    def first_hero_ids(self, limit: int = 10) -> list[int]:
        """Первые limit id героев (для ограниченной синхронизации матчапов)."""
        return [h.id for h in self.all_heroes()[:limit]]

    def meta_report(
        self, limit: int = 40, rank_tier: int | None = None,
        position: int | None = None,
    ) -> tuple[list, bool]:
        """Мета-отчёт из MetaRepository (новый контракт api-агента, R2).

        Возвращает (rows, rank_supported). Пока у get_top_meta старая
        сигнатура (limit) — TypeError -> fallback без фильтров и
        rank_supported=False: UI показывает данные и пометку о тиpax.
        """
        with self.sessionmaker() as session:
            repo = MetaRepository(session)
            try:
                return list(repo.get_top_meta(
                    limit=limit, rank_tier=rank_tier, position=position,
                )), True
            except TypeError:
                return list(repo.get_top_meta(limit)), False


def create_app_context() -> AppContext:
    """Читает настройки, инициализирует логи, БД (миграции) и все сервисы."""
    settings = Settings()
    setup_logging(settings)
    engine, sessionmaker = create_db(settings.db_url)
    migrate(engine, settings.db_url)

    settings_service = SettingsService(sessionmaker)
    draft_service = DraftService(sessionmaker)
    news_service = NewsService(sessionmaker, settings)
    validator = ValidatorService()
    opendota = OpenDotaClient(
        settings, validator, engine=engine, sessionmaker=sessionmaker,
    )
    supabase = SupabaseClient(settings, sessionmaker=sessionmaker)
    overlay_service = OverlayService(settings_service)

    return AppContext(
        settings=settings,
        engine=engine,
        sessionmaker=sessionmaker,
        settings_service=settings_service,
        draft_service=draft_service,
        news_service=news_service,
        opendota=opendota,
        supabase=supabase,
        overlay_service=overlay_service,
    )
