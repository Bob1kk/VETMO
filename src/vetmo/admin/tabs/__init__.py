"""Вкладки VETMO Admin: обзор, sync, мета, матчапы, raw, история, настройки."""

from __future__ import annotations

from vetmo.admin.tabs.dashboard import DashboardTab
from vetmo.admin.tabs.matchups_tab import MatchupsTab
from vetmo.admin.tabs.meta_tab import MetaTab
from vetmo.admin.tabs.raw_tab import RawTab
from vetmo.admin.tabs.runs_tab import RunsTab
from vetmo.admin.tabs.settings_tab import SettingsTab
from vetmo.admin.tabs.sync_tab import SyncTab

__all__ = [
    "DashboardTab",
    "MatchupsTab",
    "MetaTab",
    "RawTab",
    "RunsTab",
    "SettingsTab",
    "SyncTab",
]
