"""Валидатор API-данных OpenDota против реальности. Контракт T-007."""

from dataclasses import dataclass


@dataclass
class ValidationResult:
    """Итог проверки записи: валидна и/или карантируется."""

    is_valid: bool
    quarantined: bool
    reason: str | None = None


@dataclass
class QuarantineRecord:
    """Запись в карантине: причина важно для отладки."""

    record: dict
    reason: str


def _quarant(reason: str) -> ValidationResult:
    """Стандартный карантинный результат."""
    return ValidationResult(is_valid=False, quarantined=True, reason=reason)


def _ok() -> ValidationResult:
    """Стандартный валидный результат."""
    return ValidationResult(is_valid=True, quarantined=False, reason=None)


class ValidatorService:
    """Проверяет сырые записи OpenDota: имена, диапазоны, URL иконок."""

    def validate_hero(self, record: dict) -> ValidationResult:
        """Имя героя не пустое; icon_url (если есть) — http(s)."""
        display = record.get("localized_name")
        name = record.get("name")
        identity = str(display or name or "").strip()
        if not identity:
            return _quarant("пустое имя героя (empty hero name)")
        icon = record.get("icon_url") or record.get("icon") or record.get("img")
        if icon:
            icon_url = str(icon).strip()
            if not (icon_url.startswith("http://") or icon_url.startswith("https://")):
                return _quarant(f"невалидный icon_url: {icon_url} (invalid icon url)")
        return _ok()

    def validate_meta(self, record: dict) -> ValidationResult:
        """win_rate и pick_rate присутствуют и в диапазоне 0..100."""
        try:
            win_rate = float(record["win_rate"])
            pick_rate = float(record["pick_rate"])
        except (KeyError, TypeError, ValueError):
            return _quarant("отсутствуют/нечисловые win_rate/pick_rate (invalid meta fields)")
        if not (0.0 <= win_rate <= 100.0):
            return _quarant(f"win_rate вне 0..100 (out of range): {win_rate}")
        if not (0.0 <= pick_rate <= 100.0):
            return _quarant(f"pick_rate вне 0..100 (out of range): {pick_rate}")
        return _ok()
