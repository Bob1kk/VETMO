"""Драфт 2-2-1: Supabase (anonymous auth) + локальный JSON-фолбэк.

Интерфейс совпадает с ``vetmo.services.draft_service.DraftService``:
MainWindow и OverlayViewModel не знают, откуда пришли данные.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from vetmo.data.supabase_heroes import SupabaseHeroRepository
from vetmo.domain.matchup import MatchupEntry, MatchupReport
from vetmo.domain.models import DraftPick, DraftSession, Hero, Pick, Team
from vetmo.domain.rank_brackets import basic_bracket_label
from vetmo.domain.rules import (
    TOTAL_PICKS,
    is_valid_step,
    position_fit,
    suggest_position,
    team_for_step,
)
from vetmo.infra.supabase_gateway import SupabaseGateway
from vetmo.services.supabase_meta import SupabaseMetaService
from vetmo.services.supabase_settings import SupabaseSettingsService

logger = logging.getLogger("vetmo.draft")

_PRIORITY_BONUS = 10.0
_POSITION_FIT_WEIGHT = 5.0
_TOOLTIP_ROWS = 5


def _drafts_path() -> Path:
    appdata = os.environ.get("APPDATA")
    base = Path(appdata) if appdata else Path.home() / ".local" / "share"
    return base / "VETMO" / "drafts.json"


def _team_on_clock(state: DraftSession) -> Team | None:
    try:
        return team_for_step(state.current_step)
    except ValueError:
        return None


class SupabaseDraftService:
    """Сессии и пики драфта, рекомендации по мете."""

    def __init__(
        self,
        gateway: SupabaseGateway,
        heroes: SupabaseHeroRepository,
        settings: SupabaseSettingsService,
        meta: SupabaseMetaService,
    ) -> None:
        self._gateway = gateway
        self._heroes = heroes
        self._settings = settings
        self._meta = meta
        self._remote_disabled = False
        self._local = self._read_local()

    # ------------------------------------------------------------ локально --
    def _read_local(self) -> dict[str, Any]:
        path = _drafts_path()
        if not path.is_file():
            return {"next_id": 1, "sessions": []}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError
            data.setdefault("next_id", 1)
            data.setdefault("sessions", [])
            return data
        except (OSError, ValueError):
            return {"next_id": 1, "sessions": []}

    def _write_local(self) -> None:
        path = _drafts_path()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(self._local, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            logger.warning("Не удалось сохранить локальный драфт")

    def _local_session(self, session_id: int | None = None) -> DraftSession:
        sessions = self._local.get("sessions", [])
        if not sessions:
            session = self._local_new_session()
            return session
        row = next(
            (item for item in sessions if item.get("id") == session_id),
            sessions[-1],
        )
        return DraftSession(
            id=int(row["id"]),
            current_step=int(row.get("current_step", 0)),
            total_picks=int(row.get("total_picks", TOTAL_PICKS)),
            picks=[DraftPick.model_validate(p) for p in row.get("picks", [])],
        )

    def _local_new_session(self) -> DraftSession:
        session_id = int(self._local.get("next_id", 1))
        self._local["next_id"] = session_id + 1
        row = {
            "id": session_id,
            "current_step": 0,
            "total_picks": TOTAL_PICKS,
            "picks": [],
        }
        self._local.setdefault("sessions", []).append(row)
        self._write_local()
        return DraftSession(id=session_id, current_step=0, total_picks=TOTAL_PICKS, picks=[])

    def _local_add_pick(
        self, session_id: int, pick: Pick, step: int,
    ) -> None:
        row = next(
            (s for s in self._local.get("sessions", []) if s.get("id") == session_id),
            None,
        )
        if row is None:
            raise ValueError(f"Сессия драфта не найдена: {session_id}")
        row.setdefault("picks", []).append(
            {"team": pick.team, "position": pick.position, "hero_id": pick.hero_id, "step": step}
        )
        row["current_step"] = min(TOTAL_PICKS, step + 1)
        self._write_local()

    # ------------------------------------------------------------- remote --
    @property
    def remote_enabled(self) -> bool:
        return not self._remote_disabled and self._gateway.user_id is not None

    def _user_id(self) -> str | None:
        if self._remote_disabled or not self._gateway.is_configured:
            return None
        return self._gateway.ensure_session()

    def _remote_latest_id(self, user_id: str) -> int | None:
        rows = self._gateway.select(
            "vetmo_drafts",
            columns="id,current_step,total_picks,started_at",
            filters={"user_id": user_id},
            order=("id", True),
            limit=1,
        )
        return int(rows[0]["id"]) if rows else None

    def _remote_state(self, user_id: str, session_id: int | None = None) -> DraftSession | None:
        if session_id is None:
            session_id = self._remote_latest_id(user_id)
        if session_id is None:
            return None
        rows = self._gateway.select(
            "vetmo_drafts",
            columns="id,current_step,total_picks",
            filters={"id": int(session_id), "user_id": user_id},
            limit=1,
        )
        if not rows:
            return None
        draft = rows[0]
        pick_rows = self._gateway.select(
            "vetmo_draft_picks",
            columns="team,position,hero_id,step",
            filters={"session_id": int(session_id)},
            order=("step", False),
            limit=20,
        )
        return DraftSession(
            id=int(draft["id"]),
            current_step=int(draft.get("current_step") or 0),
            total_picks=int(draft.get("total_picks") or TOTAL_PICKS),
            picks=[DraftPick.model_validate(row) for row in pick_rows],
        )

    # ------------------------------------------------------------- сессии --
    def start_session(self) -> DraftSession:
        """Начинает новую сессию драфта."""
        user_id = self._user_id()
        if user_id:
            try:
                rows = self._gateway.insert(
                    "vetmo_drafts",
                    [{"user_id": user_id, "current_step": 0, "total_picks": TOTAL_PICKS}],
                )
                if rows:
                    return DraftSession(
                        id=int(rows[0]["id"]), current_step=0,
                        total_picks=TOTAL_PICKS, picks=[],
                    )
            except Exception as exc:  # noqa: BLE001
                self._remote_disabled = True
                logger.info("Драфт в Supabase недоступен: %s", type(exc).__name__)
        return self._local_new_session()

    def get_state(self, session_id: int | None = None) -> DraftSession:
        """Текущее состояние; без id — последняя сессия (или новая)."""
        user_id = self._user_id()
        if user_id:
            try:
                state = self._remote_state(user_id, session_id)
                if state is not None:
                    return state
                if session_id is None:
                    return self.start_session()
            except Exception as exc:  # noqa: BLE001
                self._remote_disabled = True
                logger.info("Чтение драфта из Supabase не удалось: %s", type(exc).__name__)
        return self._local_session(session_id)

    # -------------------------------------------------------------- пики --
    def add_pick(
        self, team: str, position: int, hero_id: int,
        session_id: int | None = None,
    ) -> DraftSession:
        """Пикает команду, продвигает шаг; ошибки — ValueError."""
        state = self.get_state(session_id)
        step = state.current_step
        if not is_valid_step(step):
            raise ValueError(f"Драфт завершён (draft is finished), шаг: {step}")
        expected_team = team_for_step(step)
        if team != expected_team:
            raise ValueError(f"Сейчас пик команды {expected_team}, а не {team}")
        taken = [p.position for p in state.picks if p.team == team]
        if position in taken:
            raise ValueError(f"Позиция {position} команды {team} уже занята")
        if hero_id in {p.hero_id for p in state.picks}:
            raise ValueError(f"Герой {hero_id} уже пикнут (hero already picked)")
        if state.id is None:
            state = self.start_session()
        assert state.id is not None
        user_id = self._user_id()
        if user_id:
            try:
                self._gateway.insert(
                    "vetmo_draft_picks",
                    [{
                        "session_id": int(state.id), "team": team,
                        "position": int(position), "hero_id": int(hero_id),
                        "step": int(step),
                    }],
                )
                next_step = min(TOTAL_PICKS, step + 1)
                values: dict[str, Any] = {"current_step": next_step}
                if next_step >= TOTAL_PICKS:
                    # PostgREST понимает now() в SQL, но не в JSON.
                    from datetime import UTC, datetime
                    values["finished_at"] = datetime.now(UTC).isoformat()
                self._gateway.update(
                    "vetmo_drafts", values,
                    {"id": int(state.id), "user_id": user_id},
                )
                loaded = self._remote_state(user_id, int(state.id))
                if loaded is not None:
                    return loaded
            except Exception as exc:  # noqa: BLE001
                self._remote_disabled = True
                logger.info("Запись пика в Supabase не удалась: %s", type(exc).__name__)
                # состояние могло измениться — перечитываем локально
                state = self.get_state(session_id)
        assert state.id is not None
        self._local_add_pick(int(state.id), Pick(
            team=team, position=position, hero_id=hero_id), step)
        return self._local_session(int(state.id))

    def add_pick_auto(
        self, position: int | None, hero_id: int,
        session_id: int | None = None,
    ) -> DraftSession:
        """Команда — по правилам 2-2-1; position — наименьшая свободная."""
        state = self.get_state(session_id)
        step = state.current_step
        if not is_valid_step(step):
            raise ValueError(f"Драфт завершён (draft is finished), шаг: {step}")
        team = team_for_step(step)
        if position is None:
            taken = [p.position for p in state.picks if p.team == team]
            position = suggest_position(team, taken)
        return self.add_pick(team, position, hero_id, session_id=state.id)

    # ------------------------------------------------------- рекомендации --
    def get_recommendations(
        self, position: int, session_id: int | None = None,
        limit: int = 5, team: Team | None = None,
    ) -> list[tuple[Hero, float]]:
        """[(Hero, score)] по убыванию: мета + приоритет + позиционный фит."""
        if not 1 <= position <= 5:
            raise ValueError(f"Позиция вне 1..5: {position}")
        if limit <= 0:
            return []
        heroes = self._heroes.get_all()
        if not heroes:
            return []
        picked: set[int] = set()
        enemy_ids: set[int] = set()
        state = None
        if session_id is not None:
            try:
                state = self.get_state(session_id)
            except ValueError:
                state = None
        if state is None:
            try:
                state = self.get_state()
            except Exception:  # noqa: BLE001
                state = None
        if state is not None:
            picked = {p.hero_id for p in state.picks}
            perspective = team or _team_on_clock(state)
            if perspective is not None:
                enemy_ids = {p.hero_id for p in state.picks if p.team != perspective}
        priorities = self._settings.get_position_priorities()
        meta = self._meta.get_meta_map()
        candidates: list[tuple[Hero, float]] = []
        for hero in heroes:
            if hero.id in picked:
                continue
            row = meta.get(hero.id)
            if row is not None and row.positions and position not in row.positions:
                continue  # редкая/непопулярная позиция не должна рекомендоваться
            score = 0.0
            if row is not None:
                score += (float(row.win_rate) - 50.0) * 2.0
                score += float(row.pick_rate) * 0.1
            if hero.id in priorities.get(position, []):
                score += _PRIORITY_BONUS
            fit = position_fit(tuple(hero.roles), position)
            score += fit * _POSITION_FIT_WEIGHT
            if row is None and fit == 0.0 and hero.id not in priorities.get(position, []):
                continue
            candidates.append((hero, score))
        candidates.sort(key=lambda item: (-item[1], item[0].localized_name))
        if not enemy_ids or not candidates:
            return candidates[:limit]
        # Контрпики считаем только для верхушки: один bulk-запрос вместо
        # 127 последовательных запросов к Supabase.
        top = candidates[: max(limit * 4, 30)]
        matchup_map = self._meta.get_matchups_bulk(
            [hero.id for hero, _ in top], list(enemy_ids),
        )
        rescored: list[tuple[Hero, float]] = []
        for hero, score in top:
            for matchup in matchup_map.get(hero.id, []):
                try:
                    wr = float(matchup.get("win_rate") or 50.0)
                except (TypeError, ValueError):
                    continue
                score += (wr - 50.0) * 0.1
            rescored.append((hero, score))
        rescored.sort(key=lambda item: (-item[1], item[0].localized_name))
        return rescored[:limit]

    def get_matchup_report(
        self,
        hero_id: int,
        rank_tier: int = 0,
        patch_id: int | None = None,
    ) -> MatchupReport:
        """Три списка матчапов героя для диалога статистики.

        Источник — ``vetmo_hero_matchups`` (STRATZ, последняя полная
        неделя). Контрпики/хорошие пики — против оппонентов, связки — с
        союзниками. Позиция на матчапы не влияет: STRATZ их не разрезает
        по позициям, поэтому в подписи честно указано «все позиции».
        """
        actual, grouped, fallback = self._meta.get_matchup_highlights(
            int(hero_id), rank_tier=rank_tier, patch_id=patch_id,
        )
        lookup = {hero.id: hero for hero in self._heroes.get_all()}
        hero = lookup.get(int(hero_id))

        def entries(bucket: str) -> list[MatchupEntry]:
            result: list[MatchupEntry] = []
            for row in grouped.get(bucket, []):
                try:
                    other_id = int(row.get("vs_hero_id") or 0)
                except (TypeError, ValueError):
                    continue
                if other_id <= 0:
                    continue
                other = lookup.get(other_id)
                name = (
                    (other.localized_name or other.name)
                    if other is not None else f"Герой {other_id}"
                )
                try:
                    win_rate = float(row.get("win_rate") or 0.0)
                    match_count = int(row.get("match_count") or 0)
                except (TypeError, ValueError):
                    continue
                result.append(MatchupEntry(
                    hero_id=other_id,
                    name=name,
                    internal_name=other.name if other is not None else None,
                    icon_url=other.icon_url if other is not None else None,
                    win_rate=win_rate,
                    match_count=match_count,
                    sample_reliable=bool(row.get("sample_reliable")),
                ))
            return result

        counters = entries("counter")
        good_picks = entries("good")
        synergies = entries("synergy")
        warning: str | None = None
        if not (counters or good_picks or synergies):
            warning = (
                "Матчапы ещё не синхронизированы. Запустите "
                "tools/sync_stratz.py, чтобы заполнить их."
            )
        elif fallback:
            warning = (
                "Для выбранного рангового среза пока нет матчапов — "
                "показан общий срез по всем рангам."
            )
        elif any(
            not entry.sample_reliable
            for entry in counters + good_picks + synergies
        ):
            warning = (
                "У части строк меньше 500 матчей — такие строки добавлены "
                "только потому, что надёжных было недостаточно."
            )

        return MatchupReport(
            hero_id=int(hero_id),
            hero_name=(
                (hero.localized_name or hero.name)
                if hero is not None else f"Герой {hero_id}"
            ),
            rank_tier=int(rank_tier or 0),
            bracket=actual,
            bracket_label=basic_bracket_label(actual),
            period=self._meta.get_period(),
            counters=counters,
            good_picks=good_picks,
            synergies=synergies,
            fallback_to_all=fallback,
            warning=warning,
        )

    def get_matchup_tooltip(
        self, hero_id: int,
    ) -> tuple[list[tuple[str, float]], list[tuple[str, float]]] | None:
        """(strong, weak) для тултипа: [(имя, Δ winrate)] или None."""
        rows = self._meta.get_matchups(hero_id)
        if not rows:
            return None
        lookup = {hero.id: hero for hero in self._heroes.get_all()}
        strong: list[tuple[str, float]] = []
        weak: list[tuple[str, float]] = []
        for row in rows:
            try:
                vs_id = int(row.get("vs_hero_id") or 0)
                wr = float(row.get("win_rate") or 0.0)
            except (TypeError, ValueError):
                continue
            hero = lookup.get(vs_id)
            if hero is None:
                continue
            name = hero.localized_name or hero.name
            if wr >= 50.0:
                strong.append((name, round(wr - 50.0, 2)))
            else:
                weak.append((name, round(50.0 - wr, 2)))
        strong.sort(key=lambda item: -item[1])
        weak.sort(key=lambda item: -item[1])
        if not strong and not weak:
            return None
        return strong[:_TOOLTIP_ROWS], weak[:_TOOLTIP_ROWS]


__all__ = ["SupabaseDraftService"]
