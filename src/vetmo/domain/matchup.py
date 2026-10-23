"""Контракт матчапов для диалога статистики героя."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class MatchupEntry:
    """Один герой в списке контрпиков/хороших пиков/связок."""

    hero_id: int
    name: str = ""
    internal_name: str | None = None
    icon_url: str | None = None
    win_rate: float = 0.0
    match_count: int = 0
    sample_reliable: bool = False


@dataclass
class MatchupReport:
    """Три десятки матчапов героя для выбранного рангового среза."""

    hero_id: int
    hero_name: str
    rank_tier: int = 0
    bracket: str = "ALL"
    bracket_label: str = "все ранги"
    period: str | None = None
    counters: list[MatchupEntry] = field(default_factory=list)
    good_picks: list[MatchupEntry] = field(default_factory=list)
    synergies: list[MatchupEntry] = field(default_factory=list)
    fallback_to_all: bool = False
    warning: str | None = None

    @property
    def total(self) -> int:
        """Сколько строк всего (для тестов/пустого состояния)."""
        return len(self.counters) + len(self.good_picks) + len(self.synergies)


__all__ = ["MatchupEntry", "MatchupReport"]
