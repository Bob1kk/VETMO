"""Надёжность мета-строки: RPC может не отдавать sample_reliable."""

from vetmo.services.supabase_meta import _to_meta_row


def _row(match_count: int, sample_reliable: bool | None = None) -> dict:
    row = {"hero_id": 1, "name": "Wraith King", "match_count": match_count}
    if sample_reliable is not None:
        row["sample_reliable"] = sample_reliable
    return row


def test_reliability_derived_from_match_count_when_rpc_omits_flag() -> None:
    assert _to_meta_row(_row(12_000)).sample_reliable is True
    assert _to_meta_row(_row(49)).sample_reliable is False


def test_explicit_db_flag_wins() -> None:
    assert _to_meta_row(_row(12_000, False)).sample_reliable is False
    assert _to_meta_row(_row(10, True)).sample_reliable is True
