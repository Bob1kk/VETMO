# QA упаковки VETMO и VETMO Admin (T-114)

Дата: 2026-10-23, ветка `release/public-installer`.
Последняя пересборка: 2026-10-23 01:50–01:52, после добавления доски пиков
в оверлей и отдельного установщика Admin.
Сборка: `.\scripts\build_release.ps1 -SkipTests` (тесты прогонялись отдельно:
226 passed). Python 3.13.9, PyInstaller 6.22.3, Inno Setup 6.7.3.

## Что изменилось в этой сборке

- **Доска пиков в оверлее (FR-004).** У каждой команды 5 кликабельных клеток
  (позиции 1–5), клик открывает диалог выбора героя с фильтром по атрибутам
  (`str`/`agi`/`int`/`all`) и поиском. Под клетками — блок «ПОДСКАЗКИ»:
  лучшие уникальные герои команды по всем позициям, с учётом уже выбранных
  пиков. Крестик в клетке убирает пик.
- **Перетаскивание оверлея.** Шапка окна перемещает оверлей; новая позиция
  сохраняется в настройках (`SupabaseSettingsService.set_overlay_position`).
- **Запись пика в произвольную клетку.** `SupabaseDraftService.set_pick` /
  `clear_pick` не требуют порядка 2-2-1, запрещают дубли героев и работают
  через локальный JSON-фолбэк при недоступном Supabase.
- **Отдельный установщик Admin.** `installer/VETMO-Admin.iss` +
  `installer/ADMIN-SETUP.txt`; пользовательский установщик не изменился по
  смыслу, но пересобран вместе с общим сценарием.
- **Admin: логирование и `--self-check`.** Admin теперь вызывает
  `setup_logging` (раньше лог не создавался вовсе) и умеет проверять
  конфигурацию без GUI: `VETMO-Admin.exe --self-check` → код 2, если секретов
  нет, без модальных диалогов.

## Сборочные файлы

- `vetmo.spec` — пользовательское приложение, entry `src/vetmo/main.py`, результат `dist/VETMO.exe`.
  - `_EXCLUDES` содержит `vetmo.admin`, `vetmo.infra.sync_settings`,
    `vetmo.services.stratz_client`, `vetmo.services.stratz_sync`,
    `vetmo.services.stratz_aggregate` — пользовательская сборка не содержит admin/sync-код.
- `vetmo-admin.spec` — Admin, entry `src/vetmo/admin/main.py`, результат `dist/VETMO-Admin.exe`.
  - `datas`: `src/vetmo/data/heroes_seed.json` → `vetmo/data/heroes_seed.json`, `vetmo_icon.ico` и `vetmo_icon.bmp` в корень бандла.
  - `hiddenimports`: `logging.config`, `logging.handlers`.
  - Миграции Alembic Admin не нужны: `vetmo.admin` не импортирует `vetmo.data.db`/Alembic; сборка и запуск без них проходят.
  - Секретов и путей к `secrets.env` в спеке нет.
- `installer/VETMO.iss` — установщик игрового клиента: per-user,
  `%LOCALAPPDATA%\Programs\VETMO`, без прав администратора.
- `installer/VETMO-Admin.iss` — установщик Admin: per-user,
  `%LOCALAPPDATA%\Programs\VETMO Admin`; создаёт пустой `%APPDATA%\VETMO`
  и кладёт `ADMIN-SETUP.txt`, секреты не копирует.
- `scripts/build_release.ps1` — одна команда: тесты (pytest/ruff/mypy) → оба exe →
  проверки состава и значений секретов → smoke → оба установщика →
  тихая установка/удаление каждого → `release/SHA256SUMS.txt`.
  - Пользовательский smoke: запуск с чистым `APPDATA`, проверка живого процесса,
    создания лога и отсутствия `secrets.env`/`.env`.
  - Admin smoke: `VETMO-Admin.exe --self-check` с заведомо отсутствующим
    `VETMO_SYNC_SECRETS_FILE` — ожидается код 2, запись `Self-check` в логе
    и отсутствие диалогов (иначе процесс завис бы в неинтерактивной сессии).

## Команды сборки

```powershell
.\scripts\build_release.ps1              # тесты + exe + установщики + проверки
.\scripts\build_release.ps1 -SkipTests   # только пересборка артефактов
```

Сборка завершилась с кодом `0`: «Build complete» для обеих PyInstaller-сборок,
«Successful compile» для обоих установщиков.

## Размеры и контрольные суммы артефактов

| Файл | Размер, байт | Размер, МиБ | SHA256 |
|---|---:|---:|---|
| `dist/VETMO.exe` | 67 567 628 | 64,44 | `b7ac896dff1596e1a958c096b8bec38fa0a67f100bff14e07cc20bb47b6b1397` |
| `dist/VETMO-Admin.exe` | 69 374 100 | 66,16 | `ac78d653d27d7b3c20d89e2c95d18cbf7714dba29903dd2fd6e4cd1b4cdcdee1` |
| `release/VETMO-Setup-0.1.0.exe` | 68 667 404 | 65,49 | `578c106f42003995749e477ab3ba8365595ed6434987b9673aff9dd61919aaa6` |
| `release/VETMO-Admin-Setup-0.1.0.exe` | 70 601 884 | 67,33 | `4c26d260d31ed4bd2a6136d7906771608dc18f5446c98054d7f30fc5b1e499eb` |

Те же значения записаны скриптом в `release/SHA256SUMS.txt`.
Установщики и `SHA256SUMS.txt` коммитятся в ветку (исключение в `.gitignore`),
чтобы пользователи скачивали их прямо из `release/`; `dist/` и `build/`
не коммитятся.

## Проверка состава `dist/VETMO.exe`

Метод: побайтовый поиск UTF-8 подстрок + список модулей через
`python -m PyInstaller.utils.cliutils.archive_viewer -r -b`.

| Проверка | Результат |
|---|---|
| Запрещённые строки (`service_role`, `stratz_sync`, `stratz_client`, `VETMO_SYNC_SERVICE_KEY`, `VETMO_SYNC_STRATZ_TOKEN`, `vetmo.admin`, `vetmo.infra.sync_settings`) | не найдены |
| Запрещённые модули (`vetmo.admin`, `vetmo.infra.sync_settings`, `vetmo.services.stratz_client`, `vetmo.services.stratz_sync`, `vetmo.services.stratz_aggregate`) | отсутствуют |
| Обязательный модуль `vetmo.infra.public_config` (публичные URL/anon-ключ Supabase) | присутствует |
| Значения секретов из `%APPDATA%\VETMO\secrets.env` (3 значения) | не найдены |

## Проверка состава `dist/VETMO-Admin.exe`

| Проверка | Результат |
|---|---|
| Обязательные модули `vetmo.admin`, `vetmo.services.stratz_sync` | присутствуют |
| Значения секретов из `secrets.env` (3 значения) | не найдены |

Пути к `secrets.env` и значения ключей в спеке Admin отсутствуют: файл
читается только в рантайме через `vetmo.infra.sync_settings`.

## Smoke-запуски

| Проверка | Результат |
|---|---|
| `VETMO.exe` с чистым `APPDATA`, `QT_QPA_PLATFORM=offscreen`, 12 с | процесс жив, лог `VETMO\logs\vetmo.log` создан, `Traceback` в логе нет, `secrets.env`/`.env` не созданы |
| `VETMO-Admin.exe --self-check` с несуществующим `VETMO_SYNC_SECRETS_FILE` | код возврата 2, в логе запись `Self-check: секреты недоступны`, файл секретов не создан |
| Установленный `VETMO.exe` (после тихой установки) | smoke пройден |
| Установленный `VETMO-Admin.exe --self-check` | код 2, лог создан |

Замер «холодный старт < 3 с» в неинтерактивной сессии не перепроверялся:
опрос `MainWindowHandle` не видит окно (особенность сессии); NFR-001
проверялся в T-020.

## Установщики (Inno Setup 6.7.3)

| Установщик | Каталог | Проверка |
|---|---|---|
| `VETMO-Setup-0.1.0.exe` | `%LOCALAPPDATA%\Programs\VETMO` | `/VERYSILENT /NOICONS /DIR=...` → exe на месте → smoke → `unins000.exe /VERYSILENT` → каталог удалён |
| `VETMO-Admin-Setup-0.1.0.exe` | `%LOCALAPPDATA%\Programs\VETMO Admin` | то же + `--self-check` установленного exe |

Оба установщика per-user (`PrivilegesRequired=lowest`), поддерживают русский и
английский языки, создают ярлыки в «Пуск» и (опционально) на рабочем столе.
Установщики и exe не подписаны: для публичного релиза нужна Authenticode-подпись.

## Тесты

`pytest tests/ -q` — 226 passed, включая:

- `tests/integration/test_overlay_window.py` — клетки 1..5, клик по клетке,
  крестик очистки, подсказки, `show_dire`, перетаскивание;
- `tests/integration/test_hero_pick_dialog.py` — фильтр по атрибутам, поиск,
  предвыбор текущего героя;
- `tests/unit/test_overlay_board_service.py` — `set_pick`/`clear_pick`:
  произвольный порядок, замена, запрет дублей, очистка;
- `tests/unit/test_overlay_vm_suggestions.py` — dedupe и сортировка подсказок;
- `tests/admin/test_main.py` — `--self-check` без секретов (код 2 + лог).

`ruff check src/ tests/` и `mypy src/vetmo` — без замечаний.

## Замечания

- Перед пересборкой нужно закрыть запущенные `VETMO`/`VETMO-Admin`: скрипт
  проверяет процессы и падает с понятным сообщением, если они остались.
- В `build/vetmo-admin/warn-vetmo-admin.txt` остаются стандартные
  предупреждения PyInstaller об опциональных модулях (`rich`, `boto3`,
  `azure`, `gevent`, `eventlet`, `tzdata` и т.п.). Они не входят в рантайм
  Admin; запуск exe подтверждает отсутствие ошибок импорта.
- `curl_cffi` (нужен `stratz_client`) и его DLL корректно попали в
  Admin-сборку; дополнительных `hiddenimports`/`datas` не потребовалось.
- Проверка секретов — побайтовая; она не заменяет аудит рантайма, но
  подтверждает, что значения ключей не упакованы в артефакты.
- Не перенаправляйте вывод `build_release.ps1` через `2>&1 | Tee-Object`:
  при `$ErrorActionPreference = "Stop"` stderr PyInstaller превращается в
  `NativeCommandError` и валит сборку. Запускайте скрипт напрямую.
