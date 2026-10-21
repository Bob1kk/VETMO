# QA упаковки VETMO и VETMO Admin (T-114)

Дата: 2026-10-21, ветка `beta2`.
Последняя пересборка: 2026-10-21 19:16–19:19, после коммита `dc050ae`.

## Пользовательский установщик и сборка без секретов

Проверка выполнена после пересоздания локального `.venv` на Python 3.12.6
(PyInstaller 6.22.3). Сборка запускалась через
`.\scripts\build_release.ps1 -IsccPath <путь к ISCC.exe>`.

- `dist/VETMO.exe` — 66 469 677 байт; SHA256
  `72af8207b589b09caa416752e9ccc3f0a4c4bc60de9e57a44354143aeff3062f`.
- `release/VETMO-Setup-0.1.0.exe` — 67 562 747 байт; SHA256
  `56bcd1c1edbbf55c3e44b29b587eb2de46e961d294791b0e1daeb19505e7a0d8`.
- Установщик per-user (`%LOCALAPPDATA%\Programs\VETMO`), без прав
  администратора; ярлык в «Пуск», опционально на рабочий стол.
- Тихая установка, запуск установленного exe и тихое удаление прошли.
- В exe присутствует `vetmo.infra.public_config`, отсутствуют
  `vetmo.admin`, `vetmo.infra.sync_settings`, `vetmo.services.stratz_client`,
  `vetmo.services.stratz_sync`, `vetmo.services.stratz_aggregate`.
- Smoke с временным пустым `APPDATA` (без `.env`/`secrets.env`): процесс жив,
  лог создан, `Traceback` нет; запросы `vetmo_heroes` и
  `vetmo_get_meta_report` вернули HTTP 200. Файлы секретов приложение не создало.
- Анонимная авторизация Supabase возвращает 422; это ожидаемо для текущей
  схемы. Настройки и драфты сохраняются локально (fallback).
- Артефакты не подписаны Authenticode; для публичного релиза нужен
  код-сертификат, иначе возможен warning SmartScreen.

## Пересборка после `dc050ae`

Коммит `dc050ae` — `fix(sync): tolerate missing sync_runs trace columns`:
если в удалённой БД нет колонок `trigger_source`/`request_id`, sync больше не
падает. `_supports_column` проверяет наличие колонки, а значения пишутся в
`details` (jsonb); отдельные поля заполняются только после миграции.

- `VETMO-Admin.exe` пересобран из текущего дерева (`beta2`, `dc050ae`).
- В PYZ Admin-сборки проверено наличие fallback-кода: из `vetmo.services.stratz_sync`
  извлечены `_supports_column`, `_optional_field`, `_trace_details` и строки
  `trigger_source`/`request_id`.
- `VETMO.exe` пересобран для чистоты, хотя пользовательский код и `vetmo.spec`
  в `dc050ae` не менялись.

Реальный meta-sync через `SyncRunner` прошёл: `run id 14`, `status=ok`,
patch `7.41f` (id 190), `rows_meta=6858`, 54 среза, 0 ошибок;
`trigger_source` и `request_id` сохранены в `details`.

## Окружение

- Python: 3.13.9 (`.\.venv\Scripts\python.exe`)
- PyInstaller: 6.22.3
- Платформа: Windows, one-file GUI-сборки (`console=False`)
- PySide6, supabase-py, curl_cffi — из `.venv`

## Сборочные файлы

- `vetmo.spec` — пользовательское приложение, entry `src/vetmo/main.py`, результат `dist/VETMO.exe`.
- `vetmo-admin.spec` — Admin, entry `src/vetmo/admin/main.py`, результат `dist/VETMO-Admin.exe`.
  - `datas`: `src/vetmo/data/heroes_seed.json` → `vetmo/data/heroes_seed.json`, `vetmo_icon.ico` и `vetmo_icon.bmp` в корень бандла.
  - `hiddenimports`: `logging.config`, `logging.handlers`.
  - Миграции Alembic Admin не нужны: `vetmo.admin` не импортирует `vetmo.data.db`/Alembic; сборка и запуск без них проходят.
  - Секретов и путей к `secrets.env` в спеке нет.
- В `vetmo.spec` в `_EXCLUDES` добавлены `vetmo.admin`, `vetmo.infra.sync_settings`, `vetmo.services.stratz_client`, `vetmo.services.stratz_sync`, `vetmo.services.stratz_aggregate` — пользовательская сборка не содержит admin/sync-код.

## Команды сборки

```powershell
.\.venv\Scripts\python.exe -m PyInstaller vetmo-admin.spec --noconfirm
.\.venv\Scripts\python.exe -m PyInstaller vetmo.spec --noconfirm
```

Обе пересборки завершились с кодом `0` («Build complete»).

## Размеры артефактов

| Файл | Размер, байт | Размер, МиБ | Время сборки |
|---|---:|---:|---|
| `dist/VETMO.exe` | 67 547 183 | 64,42 | 2026-10-21 19:19:19 |
| `dist/VETMO-Admin.exe` | 64 472 187 | 61,49 | 2026-10-21 19:17:27 |

## Побайтовый поиск строк в `dist/VETMO.exe`

Метод: чтение файла в байтах и поиск UTF-8 подстрок. Ожидалось `False` для всех маркеров.

| Маркер | Найдено |
|---|---|
| `service_role` | False |
| `stratz_sync` | False |
| `stratz_client` | False |
| `VETMO_SYNC_SERVICE_KEY` | False |
| `vetmo.admin` | False |
| `vetmo.services.stratz_sync` | False |
| `vetmo.infra.sync_settings` | False |

## Побайтовый поиск строк в `dist/VETMO-Admin.exe`

| Маркер | Найдено |
|---|---|
| `vetmo.admin` | True |
| `vetmo.services.stratz_sync` | True |

Admin-код в сборке присутствует. Дополнительно проверено извлечение
`vetmo.services.stratz_sync` из PYZ: fallback-функции `dc050ae` на месте.

## Проверка секретов

Источник: `%APPDATA%\VETMO\secrets.env` (путь получен через `vetmo.infra.sync_settings.default_secrets_path()`). Файл существует. Значения не выводились и не сохранялись в отчёт — только имена переменных и результат поиска.

| Переменная | Есть в файле | В `VETMO.exe` | В `VETMO-Admin.exe` |
|---|---|---|---|
| `VETMO_SYNC_SERVICE_KEY` | True | False | False |
| `VETMO_SYNC_STRATZ_TOKEN` | True | False | False |
| `VETMO_SYNC_SERVICE_KEY_NEW` | True | False | False |

Значения секретов не найдены ни в одном exe.

## Smoke-запуск

Оба exe запускались с `QT_QPA_PLATFORM=offscreen`, через `Start-Process -PassThru`, ожидание 8 секунд.

| exe | Процесс жив через 8 с | Код выхода | Действие |
|---|---|---|---|
| `VETMO.exe` | Да (PID 15756) | — | остановлен вместе с дочерним процессом one-file bootloader |
| `VETMO-Admin.exe` | Да (PID 6460) | — | остановлен вместе с дочерним процессом one-file bootloader |

`secrets.env` существует, поэтому Admin не показывал диалог об отсутствии секретов. Мгновенного падения с ошибкой импорта нет: процессы живы спустя 8 секунд.

Дополнительно: запуск `VETMO.exe` в обычном (не offscreen) режиме — процесс оставался жив 15 секунд. Точное время появления окна в этой сессии измерить не удалось: опрос `MainWindowHandle` не увидел окно (особенность неинтерактивной сессии), поэтому замер «холодный старт < 3 с» здесь не перепроверялся; NFR-001 проверялся в T-020.

## Замечания

- Перед пересборкой остановлены старые процессы `VETMO`/`VETMO-Admin`, включая дочерние процессы one-file bootloader, которые держали exe и мешали перезаписи.
- В `build/vetmo-admin/warn-vetmo-admin.txt` остаются стандартные предупреждения PyInstaller об опциональных модулях (`rich`, `boto3`, `azure`, `gevent`, `eventlet`, `tzdata` и т.п.). Они не входят в рантайм Admin; запуск exe подтверждает отсутствие ошибок импорта.
- `curl_cffi` (нужен `stratz_client`) и его DLL корректно попали в Admin-сборку; дополнительных `hiddenimports`/`datas` не потребовалось.
- Проверка секретов — побайтовая; она не заменяет аудит рантайма, но подтверждает, что значения ключей не упакованы в артефакты.
