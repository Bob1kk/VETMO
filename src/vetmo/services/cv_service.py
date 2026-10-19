"""CV-сервис (эксперимент): захват экрана + шаблонное совпадение иконок героев.

Контракт T-015 / FR-009:
- ``CVService.detect_picks(region) -> list[DetectedPick]``.
- Ручной override (подтверждение/исправление распознанного пика) — FR-009.
- Модуль НИКОГДА не падает наружу: отсутствие cv2/mss, ошибок захвата,
  отсутствие совпадений -> пустой список / None + warning в лог.
- Ограничение: только экранный захват (никакого парсинга памяти/сети Dota 2).
- Dota 2 должна быть в windowed/borderless режиме.

CV — эксперимент; ручной ввод пиков (T-013) приоритетнее.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy import ndarray

from vetmo.infra.logging import get_logger

logger = get_logger("vetmo.services.cv_service")

# Опциональные зависимости: модуль импортируется даже без cv2/mss.
try:  # pragma: no cover - зависит от окружения
    import cv2

    CV_OK = bool(cv2)
except Exception:  # noqa: BLE001 — cv2 may be missing entirely
    cv2 = None  # type: ignore[assignment]
    CV_OK = False

try:  # pragma: no cover - зависит от окружения
    import mss

    MSS_OK = bool(mss)
except Exception:  # noqa: BLE001 — mss may be missing entirely
    mss = None  # type: ignore[assignment]
    MSS_OK = False

try:  # pragma: no cover - httpx входит в базовые зависимости
    import httpx
except Exception:  # noqa: BLE001
    httpx = None  # type: ignore[assignment]

_DEFAULT_ICONS_DIR = Path(__file__).resolve().parents[3] / "assets" / "cache" / "icons"
_DEFAULT_MIN_CONFIDENCE = 0.82
_MAX_TEMPLATE_SIZE = 256  # шаблоны крупнее не нужны (иконки OpenDota ~256px)
_OVERLAP_THRESHOLD = 0.5  # дубликаты: перекрытие bbox > 50%


@dataclass
class DetectedPick:
    """Распознанный пик героя: id, уверенность (0..1) и bbox (x, y, w, h)."""

    hero_id: int
    confidence: float
    bbox: tuple[int, int, int, int]


class CVService:
    """Захват экрана (mss) и шаблонное совпадение иконок (OpenCV).

    Все публичные методы безопасны: возвращают ``[]`` / ``None`` / ``False``
    и логируют warning вместо выбрасывания исключений.
    """

    def __init__(
        self,
        icons_dir: Path | None = None,
        min_confidence: float = _DEFAULT_MIN_CONFIDENCE,
    ) -> None:
        self._icons_dir = Path(icons_dir) if icons_dir else _DEFAULT_ICONS_DIR
        self._icons_dir.mkdir(parents=True, exist_ok=True)
        self._min_confidence = float(min_confidence)
        self._templates: dict[int, ndarray] = {}

    # ------------------------------------------------------------------ #
    # Шаблоны
    # ------------------------------------------------------------------ #
    def add_template(self, hero_id: int, source_path_or_url: str) -> bool:
        """Загружает иконку героя (файл или URL) как шаблон.

        URL скачивается httpx в ``icons_dir/{hero_id}.png``. Любая ошибка
        -> False (не падаем). Возвращает True, если шаблон готов к матчу.
        """
        if not CV_OK:
            logger.warning("cv2 недоступен — шаблон hero_id=%s не загружен", hero_id)
            return False
        source = (source_path_or_url or "").strip()
        if not source:
            return False

        local_path: Path | None = None
        if source.lower().startswith(("http://", "https://")):
            local_path = self._download_template(hero_id, source)
        else:
            local_path = Path(source)

        if local_path is None:
            return False

        try:
            # np.fromfile вместо imread: корректно для путей с кириллицей на Windows.
            buf = np.fromfile(str(local_path), dtype=np.uint8)
            img = cv2.imdecode(buf, cv2.IMREAD_UNCHANGED)
        except Exception:  # noqa: BLE001 — any decode failure -> False
            logger.warning("Не удалось прочитать шаблон %s (hero_id=%s)", local_path, hero_id)
            return False
        if img is None or img.size == 0:
            logger.warning("Пустой шаблон %s (hero_id=%s)", local_path, hero_id)
            return False

        template = self._to_gray(img)
        if template.shape[0] > _MAX_TEMPLATE_SIZE or template.shape[1] > _MAX_TEMPLATE_SIZE:
            scale = _MAX_TEMPLATE_SIZE / float(max(template.shape[0], template.shape[1]))
            template = cv2.resize(
                template,
                (max(1, int(template.shape[1] * scale)), max(1, int(template.shape[0] * scale))),
            )
        self._templates[hero_id] = template
        return True

    def _download_template(self, hero_id: int, url: str) -> Path | None:
        """Скачивает иконку в icons_dir/{hero_id}.png; ошибка -> None."""
        if httpx is None:
            logger.warning("httpx недоступен — не скачать %s", url)
            return None
        target = self._icons_dir / f"{hero_id}.png"
        try:
            from vetmo.infra.http_client import build_http_client

            with build_http_client(timeout=httpx.Timeout(30.0)) as client:
                response = client.get(url)
            response.raise_for_status()
            target.write_bytes(response.content)
        except Exception as exc:  # noqa: BLE001 — network must not crash
            logger.warning("Скачивание шаблона hero_id=%s не удалось: %s", hero_id, exc)
            return None
        return target

    @staticmethod
    def _to_gray(img: ndarray) -> ndarray:
        """Приводит изображение (RGB/RGBA/серое) к одноканальному серому."""
        if img.ndim == 2:
            return img
        if img.shape[2] == 4:
            img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
        return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # ------------------------------------------------------------------ #
    # Захват экрана
    # ------------------------------------------------------------------ #
    def grab_screen(self, region: tuple[int, int, int, int] | None = None) -> ndarray | None:
        """Захват экрана через mss.

        ``region`` — (x, y, width, height); None -> весь первый монитор.
        Любая ошибка -> None + warning (CV ВООБЩЕ не должен падать).
        """
        if not MSS_OK:
            logger.warning("mss недоступен — захват экрана невозможен")
            return None
        try:
            with mss.mss() as sct:
                if region is None:
                    monitor = sct.monitors[1]  # основной монитор
                    left, top, width, height = (
                        int(monitor["left"]),
                        int(monitor["top"]),
                        int(monitor["width"]),
                        int(monitor["height"]),
                    )
                else:
                    left, top, width, height = (int(v) for v in region)
                if width <= 0 or height <= 0:
                    logger.warning("Некорректный регион захвата: %s", region)
                    return None
                raw = sct.grab({"left": left, "top": top, "width": width, "height": height})
        except Exception as exc:  # noqa: BLE001 — capture must never crash
            logger.warning("Захват экрана не удался (region=%s): %s", region, exc)
            return None
        frame = np.asarray(raw)  # BGRA
        if frame.size == 0:
            return None
        if CV_OK and frame.ndim == 3 and frame.shape[2] == 4:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
        return frame.copy()

    # ------------------------------------------------------------------ #
    # Распознавание
    # ------------------------------------------------------------------ #
    def detect_picks(
        self,
        screen_region: ndarray | None = None,
        min_confidence_override: float | None = None,
    ) -> list[DetectedPick]:
        """Ищет иконки героев на регионе экрана.

        ``screen_region=None`` -> захват всего экрана внутри метода.
        Отсутствие cv2/скриншота/шаблонов/совпадений -> [] (не падаем).
        """
        if not CV_OK:
            logger.warning("cv2 недоступен — detect_picks возвращает []")
            return []
        if screen_region is None:
            screen_region = self.grab_screen()
        if screen_region is None or not self._templates:
            return []

        threshold = (
            float(min_confidence_override)
            if min_confidence_override is not None
            else self._min_confidence
        )
        try:
            screen_gray = (
                cv2.cvtColor(screen_region, cv2.COLOR_BGR2GRAY)
                if screen_region.ndim == 3
                else screen_region
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Не удалось подготовить экран для матча: %s", exc)
            return []

        candidates: list[DetectedPick] = []
        for hero_id, template in self._templates.items():
            th, tw = template.shape[:2]
            if th >= screen_gray.shape[0] or tw >= screen_gray.shape[1]:
                logger.debug("Шаблон hero_id=%s больше региона — пропуск", hero_id)
                continue
            try:
                result = cv2.matchTemplate(screen_gray, template, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, max_loc = cv2.minMaxLoc(result)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Матч шаблона hero_id=%s не удался: %s", hero_id, exc)
                continue
            if float(max_val) >= threshold:
                candidates.append(
                    DetectedPick(
                        hero_id=hero_id,
                        confidence=float(max_val),
                        bbox=(int(max_loc[0]), int(max_loc[1]), tw, th),
                    )
                )
        return self._deduplicate(candidates)

    @staticmethod
    def _deduplicate(candidates: list[DetectedPick]) -> list[DetectedPick]:
        """Убирает дубликаты (перекрытие bbox > 50%) — оставляет более уверенный."""
        by_confidence = sorted(candidates, key=lambda d: d.confidence, reverse=True)
        kept: list[DetectedPick] = []
        for pick in by_confidence:
            if not any(
                CVService._overlap_ratio(pick.bbox, other.bbox) > _OVERLAP_THRESHOLD
                for other in kept
            ):
                kept.append(pick)
        return kept

    @staticmethod
    def _overlap_ratio(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
        """Отношение площади пересечения к меньшей из площадей bbox (0..1)."""
        ax, ay, aw, ah = a
        bx, by, bw, bh = b
        ix = max(0, min(ax + aw, bx + bw) - max(ax, bx))
        iy = max(0, min(ay + ah, by + bh) - max(ay, by))
        intersection = ix * iy
        smaller = min(aw * ah, bw * bh)
        return intersection / smaller if smaller > 0 else 0.0

    # ------------------------------------------------------------------ #
    # Ручной override (FR-009)
    # ------------------------------------------------------------------ #
    def apply_overrides(
        self,
        detections: list[DetectedPick],
        overrides: dict[int, int],
    ) -> list[DetectedPick]:
        """Ручной ввод заменяет/дополняет автораспознавание.

        ``overrides``: ``{hero_id_распознанный: hero_id_истинный}``.
        Геометрия и confidence сохраняются — исправляется только идентификатор.
        """
        if not overrides:
            return list(detections)
        adjusted: list[DetectedPick] = []
        for pick in detections:
            mapped = overrides.get(pick.hero_id, pick.hero_id)
            if mapped != pick.hero_id:
                adjusted.append(
                    DetectedPick(
                        hero_id=int(mapped),
                        confidence=pick.confidence,
                        bbox=pick.bbox,
                    )
                )
            else:
                adjusted.append(pick)
        unmatched = sorted(set(overrides) - {p.hero_id for p in detections})
        if unmatched:
            logger.debug("Override-ключи без детекции пропущены: %s", unmatched)
        return adjusted

    # ------------------------------------------------------------------ #
    # Вспомогательное
    # ------------------------------------------------------------------ #
    @property
    def templates(self) -> dict[int, ndarray]:
        """Загруженные шаблоны (hero_id -> серое изображение). Только чтение."""
        return dict(self._templates)

    @property
    def icons_dir(self) -> Path:
        """Каталог локальных иконок (создаётся при первом обращении)."""
        return self._icons_dir

    def __repr__(self) -> str:  # pragma: no cover - диагностическое
        return (
            f"CVService(icons_dir={self._icons_dir!s}, "
            f"min_confidence={self._min_confidence}, "
            f"templates={len(self._templates)}, "
            f"cv_ok={CV_OK}, mss_ok={MSS_OK})"
        )

