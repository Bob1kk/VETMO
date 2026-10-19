"""Тесты CV-сервиса (T-015 / FR-009, Review Focus #5).

Контракт без сети: шаблоны — только локальные файлы tmp_path; захват
экрана не вызывается реально (screen_region передаётся напрямую или
monkeypatch-им grab_screen). Любая ошибка -> [] / None / False.
"""

from pathlib import Path

import numpy as np
import pytest

from vetmo.services.cv_service import (
    CV_OK,
    MSS_OK,
    CVService,
    DetectedPick,
)

pytestmark = pytest.mark.skipif(
    not CV_OK, reason="cv2 недоступен в этом окружении",
)

RNG = np.random.default_rng(42)


def _make_service(tmp_path: Path) -> CVService:
    """CV-сервис с каталогом иконок во временном каталоге."""
    return CVService(icons_dir=tmp_path / "icons")


def _write_png(path: Path, image: np.ndarray) -> Path:
    """Записывает серый PNG через cv2 (airod — им decoded в add_template)."""
    import cv2

    ok = cv2.imwrite(str(path), image)
    assert ok, f"cv2.imwrite не смог записать {path}"
    return path


def _icon_patch(width: int = 256, height: int = 144) -> np.ndarray:
    """Детерминированная «иконка» героя (серый канал 144x256)."""
    return RNG.integers(0, 256, size=(height, width), dtype=np.uint8)


def _screen_with_patch(
    patch: np.ndarray, x: int, y: int, rows: int = 300, cols: int = 600,
) -> np.ndarray:
    """BGR-кадр 600x300 с вставленным патчем по координатам (x, y)."""
    screen = np.full((rows, cols, 3), 128, dtype=np.uint8)
    h, w = patch.shape[:2]
    screen[y:y + h, x:x + w, 0] = patch
    screen[y:y + h, x:x + w, 1] = patch
    screen[y:y + h, x:x + w, 2] = patch
    return screen


# ---------------------------------------------------------------- templates --
def test_templates_property_empty_initially(tmp_path: Path) -> None:
    """Свойство templates на новом сервисе — пустой dict (копия)."""
    service = _make_service(tmp_path)
    assert service.templates == {}
    # копия: изменение результата не влияет на сервис
    snapshot = service.templates
    snapshot[999] = np.zeros((1, 1), dtype=np.uint8)
    assert service.templates == {}


def test_add_template_from_local_file(tmp_path: Path) -> None:
    """Локальная иконка 256x144 загружается как шаблон без ресайза."""
    service = _make_service(tmp_path)
    path = _write_png(tmp_path / "icon.png", _icon_patch())
    assert service.add_template(1, str(path)) is True
    templates = service.templates
    assert set(templates) == {1}
    assert templates[1].shape == (144, 256)


def test_add_template_nonexistent_path_returns_false(tmp_path: Path) -> None:
    """Негатив (без сети): несуществующий путь -> False, шаблонов нет."""
    service = _make_service(tmp_path)
    assert service.add_template(1, str(tmp_path / "nope.png")) is False
    assert service.templates == {}


def test_add_template_empty_source_returns_false(tmp_path: Path) -> None:
    """Пустая/whitespace-строка -> False."""
    service = _make_service(tmp_path)
    assert service.add_template(1, "") is False
    assert service.add_template(1, "   ") is False


def test_add_template_url_failure_returns_false_and_no_file(
    tmp_path, monkeypatch,
) -> None:
    """URL-версия: сетевая ошибка -> False, файл в icons_dir не появляется."""

    def boom(**_kwargs):
        raise OSError("нет сети (заглушка теста)")

    monkeypatch.setattr(
        "vetmo.infra.http_client.build_http_client", boom)
    service = _make_service(tmp_path)
    assert service.add_template(7, "https://api.opendota.com/no/icon.png") \
        is False
    assert list((tmp_path / "icons").glob("*.png")) == []


# ---------------------------------------------------------------- detect --
def test_detect_without_templates_returns_empty(tmp_path: Path) -> None:
    """Нет шаблонов + экран передан -> [] (никаких исключений)."""
    service = _make_service(tmp_path)
    screen = _screen_with_patch(_icon_patch(), 0, 0)
    assert service.detect_picks(screen) == []


def test_detect_none_region_never_grabs_real_screen(
    tmp_path, monkeypatch,
) -> None:
    """screen_region=None без шаблонов -> [] и без реального захвата."""
    service = _make_service(tmp_path)
    calls: list = []

    def fake_grab(region=None):
        calls.append(region)
        return None

    monkeypatch.setattr(service, "grab_screen", fake_grab)
    assert service.detect_picks(None) == []
    assert len(calls) <= 1  # метод мог попытаться захватить приоритетно


def test_detect_finds_inserted_icon_with_bbox_and_confidence(
    tmp_path: Path,
) -> None:
    """Иконка внутри кадра -> детект с верным bbox и conf >= порога."""
    service = _make_service(tmp_path)
    patch = _icon_patch()  # один и тот же патч: шаблон == вставленный регион
    path = _write_png(tmp_path / "icon.png", patch)
    assert service.add_template(21, str(path)) is True

    x, y = 40, 30
    screen = _screen_with_patch(patch, x, y)
    picks = service.detect_picks(screen)

    assert len(picks) == 1
    assert picks[0].hero_id == 21
    assert picks[0].confidence >= service._min_confidence  # noqa: SLF001
    assert picks[0].bbox == (x, y, 256, 144)


def test_cv_match_requires_min_confidence(tmp_path: Path) -> None:
    """Review Focus #5 (часть 1): слабое совпадение отсекается порогом."""
    service = _make_service(tmp_path)
    path = _write_png(tmp_path / "icon.png", _icon_patch())
    assert service.add_template(5, str(path)) is True

    noise = RNG.integers(0, 256, size=(300, 600, 3), dtype=np.uint8)
    assert service.detect_picks(noise, min_confidence_override=0.99) == []

    # даже настоящий матч отсекается неприемлемо высоким порогом
    screen = _screen_with_patch(_icon_patch(), 10, 10)
    assert service.detect_picks(screen, min_confidence_override=1.1) == []


# ---------------------------------------------------------------- overrides --
def test_apply_overrides_remaps_hero_id_keeps_geometry(tmp_path: Path) -> None:
    """Review Focus #5 (часть 2): override меняет только hero_id."""
    service = _make_service(tmp_path)
    patch = _icon_patch()
    path = _write_png(tmp_path / "icon.png", patch)
    assert service.add_template(1, str(path)) is True
    screen = _screen_with_patch(patch, 5, 5)
    picks = service.detect_picks(screen)
    assert picks and picks[0].hero_id == 1

    corrected = service.apply_overrides(picks, {1: 77})
    assert corrected[0].hero_id == 77
    assert corrected[0].confidence == picks[0].confidence
    assert corrected[0].bbox == picks[0].bbox


def test_apply_overrides_unknown_key_is_no_op(tmp_path: Path) -> None:
    """Override по не-детектированному id не ломает список."""
    service = _make_service(tmp_path)
    original = [DetectedPick(hero_id=1, confidence=0.9, bbox=(0, 0, 8, 8))]
    assert service.apply_overrides(original, {99: 5}) == original


def test_cv_match_requires_min_confidence_and_allows_manual_override(
    tmp_path: Path,
) -> None:
    """Review Focus #5 (сводный): ложный дубль срезает порог, ручной
    override исправляет распознанного героя поверх автораспознавания.
    """
    service = _make_service(tmp_path)
    patch = _icon_patch()
    path = _write_png(tmp_path / "icon.png", patch)
    assert service.add_template(3, str(path)) is True

    noise = RNG.integers(0, 256, size=(200, 400, 3), dtype=np.uint8)
    assert service.detect_picks(noise, min_confidence_override=0.99) == []

    screen = _screen_with_patch(patch, 12, 9)
    picks = service.detect_picks(screen)
    assert [p.hero_id for p in picks] == [3]

    manual = service.apply_overrides(picks, {3: 105})
    assert [p.hero_id for p in manual] == [105]
    assert manual[0].confidence == picks[0].confidence
    assert manual[0].bbox == picks[0].bbox


# ---------------------------------------------------------------- dedup --
def test_overlapping_duplicate_detections_deduplicated_to_best(
    tmp_path: Path,
) -> None:
    """Review Focus #5: два шаблона одного патча -> одна детекция,
    остаётся более уверенный (оригинал, а не размытая копия).
    """
    import cv2

    service = _make_service(tmp_path)
    patch = _icon_patch()
    path = _write_png(tmp_path / "sharp.png", patch)
    blurry = _write_png(
        tmp_path / "blur.png",
        cv2.GaussianBlur(patch, (5, 5), 0),
    )
    assert service.add_template(1, str(path)) is True
    assert service.add_template(2, str(blurry)) is True

    screen = _screen_with_patch(patch, 15, 15)
    picks = service.detect_picks(screen)

    assert len(picks) == 1, picks
    assert picks[0].hero_id == 1  # точный патч уверённее размытой копии
    assert picks[0].bbox == (15, 15, 256, 144)


def test_deduplicate_keeps_non_overlapping_and_best_overlap() -> None:
    """Дедуп на уровне формулы: не пересекающиеся bbox остаются, дубли
    (>50% перекрытия) схлопываются в самый уверенный.
    """
    far = [
        DetectedPick(hero_id=1, confidence=0.9, bbox=(0, 0, 16, 16)),
        DetectedPick(hero_id=2, confidence=0.8, bbox=(40, 40, 16, 16)),
    ]
    assert [p.hero_id for p in CVService._deduplicate(far)] == [1, 2]  # noqa: SLF001

    overlapping = [
        DetectedPick(hero_id=1, confidence=0.9, bbox=(0, 0, 16, 16)),
        DetectedPick(hero_id=2, confidence=0.95, bbox=(0, 0, 16, 16)),
    ]
    kept = CVService._deduplicate(overlapping)  # noqa: SLF001
    assert len(kept) == 1 and kept[0].hero_id == 2


# ---------------------------------------------------------------- grab --
@pytest.mark.skipif(not MSS_OK, reason="mss недоступен")
def test_grab_screen_invalid_region_returns_none(tmp_path: Path) -> None:
    """Некорректный регион -> None без броска исключения (протокол ошибок)."""
    service = _make_service(tmp_path)
    assert service.grab_screen((-5, -5, 0, 0)) is None
