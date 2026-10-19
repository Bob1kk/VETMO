"""Тесты ValidatorService (T-007): карантин невалидных записей OpenDota."""

from vetmo.services.validator_service import ValidationResult, ValidatorService

V = ValidatorService()


def test_hero_valid_record_passes() -> None:
    """Валидная запись: is_valid=True, quarantine нет."""
    res = V.validate_hero({
        "id": 1, "name": "npc_dota_hero_antimage",
        "localized_name": "Anti-Mage",
        "icon_url": "https://cdn.opendota.com/x.png",
    })
    assert res.is_valid and res.quarantined is False and res.reason is None


def test_hero_empty_name_quarantined() -> None:
    """Пустое имя -> карантин."""
    res = V.validate_hero({"id": 1, "name": "", "localized_name": "   "})
    assert res.is_valid is False and res.quarantined is True
    assert res.reason is not None


def test_hero_missing_name_quarantined() -> None:
    """Нет имени вообще -> карантин."""
    res = V.validate_hero({"id": 1})
    assert res.is_valid is False and res.quarantined is True


def test_hero_relative_icon_url_quarantined() -> None:
    """icon_url без http(s) (например ftp://) -> карантин (клиент нормализует //)."""
    res = V.validate_hero({
        "name": "x", "localized_name": "X", "icon_url": "ftp://cdn/x.png",
    })
    assert res.is_valid is False and res.quarantined is True


def test_meta_valid_passes() -> None:
    """Мета в диапазонах -> валидна."""
    res = V.validate_meta({"win_rate": 52.3, "pick_rate": 8.9})
    assert res.is_valid and res.quarantined is False


def test_meta_win_rate_above_100_quarantined() -> None:
    """win_rate > 100 -> карантин (Review Focus #1)."""
    res = V.validate_meta({"win_rate": 120.0, "pick_rate": 5.0})
    assert res.is_valid is False and res.quarantined is True


def test_meta_negative_quarantined() -> None:
    """Отрицательный pick_rate -> карантин."""
    res = V.validate_meta({"win_rate": 50.0, "pick_rate": -1.0})
    assert res.is_valid is False and res.quarantined is True


def test_meta_missing_fields_quarantined() -> None:
    """Не хватает полей -> карантин, не исключение."""
    res = V.validate_meta({"win_rate": 50.0})
    assert res.is_valid is False and res.quarantined is True


def test_validation_result_dataclass_default() -> None:
    """Reason по умолчанию None."""
    r = ValidationResult(is_valid=True, quarantined=False)
    assert r.reason is None
