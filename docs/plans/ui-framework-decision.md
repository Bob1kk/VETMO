# Выбор UI-фреймворка VETMO (NFR-007)

**Решение:** PySide6 (утверждён по умолчанию в плане). Обоснование ниже готовит backend-agent по заданию NFR-007.

## Требования плана

- Современный, красивый, лёгкий интерфейс (NFR-007, раздел 11).
- Оверлей: borderless, always-on-top, прозрачность, click-through, не крадёт фокус (FR-004, NFR-002).
- Упаковка в один .exe (FR-012).

## Сравнение

| Критерий | PySide6 | Flet | CustomTkinter | Tauri+Web |
|---|---|---|---|---|
| Настоящий оверлей (frameless + прозрачность + click-through + stays-on-top) | Да, нативные WindowFlags | Нет (по сути веб-окно) | Ограничено Tk | Только через хаки; всегда видно в панели окон |
| Размер .exe | ~ 80–120 МБ, офлайн, всё внутри | Требует рантайм Flutter (доп. бустрап) | ~30–50 МБ | Отдельный frontend-билд + Node-тулинг, сложнее PyInstaller |
| Зависимости для CI | 1 пакет (wheel) | flet + flet runtime | 1 пакет | Node + Rust-тулинг |
| Работает без GPU/браузера | Да (native Qt) | Запускает собственный рантайм | Да | Требует WebView2 |
| Тестовый стенд | pytest-qt зрелый | Слабый | Слабый | Нужен e2e (Playwright) |
| Стилизация «современно» | QSS (CSS-подобные стили, тёмная тема) | Хорошая, но менее контролируемая | Наследует Tk:Ttk | Полная свобода (HTML/CSS) |

## Вердикт

PySide6 — единственный вариант, который нативно даёт все флаги окна, требуемые для игрового
оверлея (FramelessWindowHint, WindowStaysOnTopHint, WS_EX_TRANSPARENT/WA_TransparentForMouseEvents,
windowOpacity) и при этом упаковывается PyInstaller'ом в one-file без лишних рантаймов.
Flet и Tauri добавляют браузероподобные рантаймы и не умеют click-through, CustomTkinter
не умеет native overlay поверх полноэкранного окна.

Упаковка: PyInstaller onefile + `--collect-data PySide6`; холодный старт < 3 с достижим
(ленивый импорт CV-модуля, отложенная загрузка меты).
