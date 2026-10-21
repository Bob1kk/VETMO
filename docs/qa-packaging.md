# QA упаковки VETMO и VETMO Admin (T-114)

Дата: 2026-10-21, ветка `beta2`.

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

Обе сборки завершились с кодом `0` («Build complete»).

## Размеры артефактов

| Файл | Размер, байт | Размер, МиБ |
|---|---:|---:|
| `dist/VETMO.exe` | 67 547 316 | 64,42 |
| `dist/VETMO-Admin.exe` | 64 469 239 | 61,48 |

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

Admin-код в сборке присутствует.

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
| `VETMO.exe` | Да (PID 24436) | — | остановлен `Stop-Process` |
| `VETMO-Admin.exe` | Да (PID 7428) | — | остановлен `Stop-Process` |

`secrets.env` существует, поэтому Admin не показывал диалог об отсутствии секретов. Мгновенного падения с ошибкой импорта нет: процессы живы спустя 8 секунд.

Дополнительно: запуск `VETMO.exe` в обычном (не offscreen) режиме — процесс оставался жив 15 секунд. Точное время появления окна в этой сессии измерить не удалось: опрос `MainWindowHandle` не увидел окно (особенность неинтерактивной сессии), поэтому замер «холодный старт < 3 с» здесь не перепроверялся; NFR-001 проверялся в T-020.

## Замечания

- При первой пересборке `dist/VETMO.exe` был заблокирован двумя старыми процессами `VETMO` (PID 13540 и 15960, запущены в 16:34). Процессы остановлены, после чего сборка прошла с кодом `0`.
- В `build/vetmo-admin/warn-vetmo-admin.txt` остаются стандартные предупреждения PyInstaller об опциональных модулях (`rich`, `boto3`, `azure`, `gevent`, `eventlet`, `tzdata` и т.п.). Они не входят в рантайм Admin; запуск exe подтверждает отсутствие ошибок импорта.
- `curl_cffi` (нужен `stratz_client`) и его DLL корректно попали в Admin-сборку; дополнительных `hiddenimports`/`datas` не потребовалось.
- Проверка секретов — побайтовая; она не заменяет аудит рантайма, но подтверждает, что значения ключей не упакованы в артефакты.
