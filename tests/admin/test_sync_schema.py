"""Совместимость sync с удалённой схемой ``vetmo_sync_runs``."""

from __future__ import annotations

from typing import Any

import pytest

from vetmo.services.stratz_sync import (
    _optional_field,
    _supports_column,
    _trace_details,
)


class _Gateway:
    def __init__(self, *, rows: list[dict[str, Any]] | None = None, error: Exception | None = None) -> None:
        self.rows = rows or []
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def select(self, table: str, **kwargs: Any) -> list[dict[str, Any]]:
        self.calls.append({"table": table, **kwargs})
        if self.error is not None:
            raise self.error
        return self.rows


def test_supported_column_is_probed() -> None:
    gateway = _Gateway(rows=[{"trigger_source": None}])

    assert _supports_column(gateway, "trigger_source") is True
    assert gateway.calls == [
        {"table": "vetmo_sync_runs", "columns": "trigger_source", "limit": 1}
    ]


def test_missing_column_is_tolerated() -> None:
    gateway = _Gateway(
        error=RuntimeError(
            "column vetmo_sync_runs.trigger_source does not exist (42703)"
        )
    )

    assert _supports_column(gateway, "trigger_source") is False


def test_postgrest_schema_cache_error_is_tolerated() -> None:
    gateway = _Gateway(
        error=RuntimeError(
            "Could not find the 'request_id' column of 'vetmo_sync_runs' "
            "in the schema cache (PGRST204)"
        )
    )

    assert _supports_column(gateway, "request_id") is False


def test_other_select_errors_are_not_swallowed() -> None:
    gateway = _Gateway(error=RuntimeError("connection timeout"))

    with pytest.raises(RuntimeError, match="connection timeout"):
        _supports_column(gateway, "request_id")


def test_optional_field_only_when_column_exists_and_value_set() -> None:
    assert _optional_field(True, "request_id", "req-1") == {"request_id": "req-1"}
    assert _optional_field(False, "request_id", "req-1") == {}
    assert _optional_field(True, "request_id", None) == {}


def test_trace_details_always_keep_both_values() -> None:
    assert _trace_details("admin-app", "req-1") == {
        "trigger_source": "admin-app",
        "request_id": "req-1",
    }
    assert _trace_details(None, None) == {}
