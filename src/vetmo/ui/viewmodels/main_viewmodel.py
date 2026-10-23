"""MainViewModel: данные для лаунчера (новости/мета/настройки). Без Qt (NFR-005).

UI (MainWindow) запускает fetch_* в QThreadPool-воркере и публикует
результат через publish_* — подписчики (виджеты) получают колбэком.
"""

from collections.abc import Callable
from dataclasses import dataclass, field

from vetmo.services.draft_service import DraftService
from vetmo.services.news_service import NewsItem, NewsService
from vetmo.ui.viewmodels.callbacks import CallbackList


@dataclass
class MetaReportRow:
    """Нормализованная строка мета-отчёта (контракт MetaRow R2, задача A).

    Все значения None-able: если api-агент ещё не отдаёт поле — виджет
    рисует «—». positions — список позиций 1..5 из ролей.
    """

    hero_id: int
    name: str = ""
    internal_name: str | None = None
    icon_url: str | None = None
    win_rate: float | None = None
    delta_win: float | None = None
    pick_rate: float | None = None
    delta_pick: float | None = None
    ban_rate: float | None = None
    delta_ban: float | None = None
    positions: list[int] = field(default_factory=list)
    position_details: dict[int, object] = field(default_factory=dict)
    patch_version: str | None = None
    primary_attr: str = ""
    attack_type: str = ""
    sample_reliable: bool = False


@dataclass
class MetaReport:
    """Мета-отчёт: строки + версия патча + поддержка ранговых фильтров."""

    rows: list[MetaReportRow] = field(default_factory=list)
    patch_version: str | None = None
    rank_supported: bool = True
    period: str | None = None


@dataclass
class _HeroAccess:
    """Утилита доступа к полям героя-объекта или dict (MetaRow.hero)."""

    source: object

    def get(self, key: str, default: object = None) -> object:
        source = self.source
        if source is None:
            return default
        if isinstance(source, dict):
            return source.get(key, default)
        return getattr(source, key, default)


def _as_float(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _as_int(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[call-overload]
    except (TypeError, ValueError):
        return None


_ROLE_TO_POSITION: dict[str, list[int]] = {
    "carry": [1],
    "midlaner": [2],
    "midlane": [2],
    "mid": [2],
    "offlaner": [3],
    "offlane": [3],
    "off": [3],
    "support": [4, 5],
    "softsupport": [4],
    "soft support": [4],
    "hardsupport": [5],
    "hard support": [5],
}


def _positions_from_roles(roles: object) -> list[int]:
    """Позиции 1..5 из ролей героя (fallback, если MetaRow без positions)."""
    positions: set[int] = set()
    raw = roles if isinstance(roles, (list, tuple)) else []
    for role in raw:
        lowered = str(role).strip().lower()
        mapped = _ROLE_TO_POSITION.get(
            lowered, _ROLE_TO_POSITION.get(lowered.replace("_", " "), []))
        positions.update(mapped)
    return sorted(positions)


def _field(row: object, key: str, default: object = None) -> object:
    """Поле MetaRow-подобного объекта или dict."""
    if row is None:
        return default
    if isinstance(row, dict):
        return row.get(key, default)
    return getattr(row, key, default)


def _normalize_meta_row(row: object) -> MetaReportRow | None:
    """MetaRow api-агента ИЛИ старый tuple (Hero, win_rate, pick_rate) -> строка.

    Пока новый контракт не появился в рантайме, работаем по старому
    репозиторию: недостающие поля остаются None, ничего не падает.
    """
    if row is None:
        return None
    if isinstance(row, (tuple, list)):
        if len(row) < 3:
            return None
        return _normalize_meta_row({
            "hero": row[0],
            "win_rate": row[1],
            "pick_rate": row[2],
        })
    hero = _HeroAccess(_field(row, "hero"))
    hero_id = _as_int(_field(row, "hero_id")) or _as_int(hero.get("id")) or 0
    name = str(
        hero.get("localized_name")
        or hero.get("name")
        or _field(row, "name")
        or "",
    )
    internal_name = (
        str(_field(row, "internal_name") or hero.get("name") or "") or None
    )
    positions: list[int] = []
    raw_positions = _field(row, "positions")
    if isinstance(raw_positions, (list, tuple)):
        positions = sorted(
            {
                p
                for p in (_as_int(x) for x in raw_positions)
                if p is not None and 1 <= p <= 5
            }
        )
    if not positions:
        positions = _positions_from_roles(hero.get("roles"))
    raw_details = _field(row, "position_stats")
    position_details: dict[int, object] = {}
    if isinstance(raw_details, dict):
        for key, value in raw_details.items():
            position = _as_int(key)
            if position is not None and 1 <= position <= 5:
                position_details[position] = value
    return MetaReportRow(
        hero_id=hero_id,
        name=name or f"Герой {hero_id}",
        internal_name=internal_name,
        icon_url=str(_field(row, "icon_url") or hero.get("icon_url") or "") or None,
        win_rate=_as_float(_field(row, "win_rate")),
        delta_win=_as_float(_field(row, "delta_win")),
        pick_rate=_as_float(_field(row, "pick_rate")),
        delta_pick=_as_float(_field(row, "delta_pick")),
        ban_rate=_as_float(_field(row, "ban_rate")),
        delta_ban=_as_float(_field(row, "delta_ban")),
        positions=positions,
        position_details=position_details,
        patch_version=str(_field(row, "patch_version") or "") or None,
        primary_attr=str(
            _field(row, "primary_attr") or hero.get("primary_attr") or ""),
        attack_type=str(
            _field(row, "attack_type") or hero.get("attack_type") or ""),
        sample_reliable=bool(_field(row, "sample_reliable") or False),
    )


class MainViewModel:
    """Состояние лаунчера: новости, мета и драфт."""

    def __init__(
        self,
        news_service: NewsService,
        draft_service: DraftService,
        meta_report_loader: Callable[..., tuple[list[object], bool]] | None = None,
    ) -> None:
        self._news = news_service
        self._draft = draft_service
        # meta_report_loader: callable(limit, rank_tier, position) ->
        #     (rows, rank_supported) — AppContext.meta_report.
        self._meta_report_loader: Callable[..., tuple[list[object], bool]] | None = (
            meta_report_loader
        )

        self.news_updated = CallbackList()      # (list[NewsItem], is_online)
        self.meta_updated = CallbackList()      # (MetaReport,)
        self.draft_updated = CallbackList()     # (DraftSession,)

    # --- запросы данных (worker-поток) ---
    def fetch_news(self, limit: int = 5) -> tuple[list[NewsItem], bool]:
        """Новости патчей + статус сети (offline fallback из БД внутри сервиса)."""
        return self._news.get_latest_patch_news(limit)

    def fetch_meta_report(
        self, limit: int = 40, rank_tier: int | None = None,
        position: int | None = None,
    ) -> MetaReport:
        """Мета-отчёт с фильтрами ранга/позиции (текущий патч)."""
        if self._meta_report_loader is None:
            raise RuntimeError("Синхронизация меты недоступна")
        result = self._meta_report_loader(
            limit=limit, rank_tier=rank_tier, position=position,
        )
        raw_rows, rank_supported = result[0], result[1]
        period = result[2] if len(result) > 2 else None
        rows = [
            normalized
            for normalized in (_normalize_meta_row(row) for row in raw_rows)
            if normalized is not None
        ]
        if not rank_supported and position is not None:
            rows = [row for row in rows if position in row.positions]
        return MetaReport(
            rows=rows,
            patch_version=self._patch_version(rows),
            rank_supported=rank_supported,
            period=period,
        )

    def _patch_version(self, rows: list[MetaReportRow]) -> str | None:
        """Версия патча: из строки MetaRow, иначе из мета-сводки."""
        for row in rows:
            if row.patch_version:
                return row.patch_version
        try:
            return self._news.get_meta_summary(limit=1).patch_version
        except Exception:  # noqa: BLE001 — патч не критичен для отчёта
            return None

    def fetch_draft_state(self):
        """Состояние последней сессии драфта (авто-создание внутри сервиса)."""
        return self._draft.get_state()

    # --- публикация результата (UI-поток) ---
    def publish_news(self, items: list[NewsItem], is_online: bool) -> None:
        """Рассылает новости подписчикам."""
        self.news_updated.emit(items, is_online)

    def publish_meta_report(self, report: MetaReport) -> None:
        """Рассылает мета-отчёт подписчикам."""
        self.meta_updated.emit(report)

    def publish_draft_state(self, state) -> None:
        """Рассылает состояние драфта подписчикам."""
        self.draft_updated.emit(state)
