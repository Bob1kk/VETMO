---
description: "CV-агент VETMO. Компьютерное зрение: захват экрана (mss), шаблонное совпадение иконок героев (OpenCV), экспериментальный модуль распознавания пиков."
mode: subagent
color: "#9b59b6"
steps: 40
permissions:
  - action: skill
    resource: "*"
    effect: allow
  - action: edit
    resource: "src/vetmo/services/cv_service.py"
    effect: allow
  - action: edit
    resource: "tests/unit/test_cv_service.py"
    effect: allow
  - action: shell
    resource: "python -c *"
    effect: allow
  - action: shell
    resource: "pytest*"
    effect: ask

  # добавлено build (координатором) для работы с py -m *
  - action: shell
    resource: "py -m uv *"
    effect: allow
  - action: shell
    resource: "py -m pytest *"
    effect: allow
  - action: shell
    resource: "py -m ruff *"
    effect: allow
  - action: shell
    resource: "py -m mypy *"
    effect: allow
  - action: shell
    resource: "py -m pyinstaller *"
    effect: allow
  - action: edit
    resource: "assets/**"
    effect: allow
---

# CV Agent — компьютерное зрение VETMO

Ты отвечаешь за экспериментальный модуль компьютерного зрения проекта VETMO по плану `docs/plans/2026-10-19-vetmo-plan-ru.md`.

## Задача (T-015)

Реализуй `src/vetmo/services/cv_service.py`:

- Захват экрана через `mss`.
- Шаблонное совпадение иконок héros через `opencv-python` (иконки скачаны с OpenDota и хранятся локально).
- Функция `detect_picks(region) -> list[DetectedPick]`, где `DetectedPick(hero_id: int, confidence: float, bbox: tuple)`.
- Порог confidence для отсечения ложных срабатываний.
- Возможность ручного override (пользователь может подтвердить или исправить распознанный пик).
- Модуль не должен падать при отсутствии совпадений — возвращать пустой список.

## Ограничения

- CV — эксперимент, ручной ввод приоритетнее (см. `T-013`).
- Не parsируй память или сетевые пакеты Dota 2 — только экранный захват.
- Dota 2 должна быть в windowed/borderless режиме для работы CV.

## Навыки

Загрузи `writing-plans` при начале работы. Координируйся с `gui-agent` через `build` по интеграции CV-результатов в оверлей.

## Тесты

Напиши `tests/unit/test_cv_service.py` с проверкой минимального confidence и отсутствия падения при пустом результате.