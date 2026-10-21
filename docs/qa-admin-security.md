# QA: VETMO Admin — тесты и безопасность (T-112, T-113)

**Дата:** 2026-10-21  
**Ветка:** `beta2`  
**Репозиторий:** `C:\Users\pavel\OneDrive\Документы\Default Project`  
**Окружение:** Python 3.13.9, `.venv`, pytest 8.x, pytest-qt, PySide6 (offscreen).

---

## 1. Итог

| Проверка | Результат | Команда |
|---|---|---|
| Полный прогон тестов | **192 passed** за 16.42 s, 0 failed, 0 skipped | `.\.venv\Scripts\python.exe -m pytest` |
| Тесты Admin (`tests/admin/`) | **38 passed** за 1.54 s | `.\.venv\Scripts\python.exe -m pytest tests/admin -v --no-header` |
| Ruff (admin + новые тесты) | **All checks passed** | `.\.venv\Scripts\python.exe -m ruff check tests/admin src/vetmo/admin` |
| Mypy (admin + тесты) | 10 ошибок, все в ранее существовавших `test_ui_smoke.py` / `test_workers.py`; новые тесты ошибок не добавили | `.\.venv\Scripts\python.exe -m mypy src/vetmo/admin tests/admin` |
| Секреты в отслеживаемых файлах | значений не найдено | `git grep` (см. §3) |
| `.gitignore` | секретные файлы игнорируются | `git check-ignore -v ...` |
| RLS Supabase | SELECT разрешён, INSERT для `anon` запрещён (401) | §4 |
| Entry point пользователя | не импортирует Admin/STRATZ sync | §5 |
| Строки в `dist/VETMO.exe` | `service_role`, `stratz_sync`, `stratz_client`, `VETMO_SYNC_SERVICE_KEY`, `vetmo.admin` отсутствуют | §6 |

Падений, связанных с таймингом (`test_main_window_created_and_shown_under_3s`), не было:
полный прогон прошёл с первого раза. Отдельный перезапуск не потребовался.

---

## 2. Добавленные тесты (T-112)

| Файл | Покрытие |
|---|---|
| `tests/admin/test_repository.py` | `latest_patch`, `last_run`, `list_runs`, `heroes`-join, фильтры `meta_rows` (патч / `window_days` / ранг / позиция), поиск по `localized_name` и `name` без учёта регистра, лимит после поиска, fallback `hero_<id>`, `matchups` с явным и вычисленным `patch_id`, `ban_stats`, `gateway` |
| `tests/admin/test_context.py` | отсутствие `secrets.env`, отсутствие `VETMO_SYNC_SERVICE_KEY`, успешная сборка `AdminContext`, нормализация URL (`/rest/v1`), приоритет переменных окружения над файлом |
| `tests/admin/test_security.py` | в `vetmo/main.py` и `vetmo/ui/**` нет импортов `vetmo.admin`, `stratz_sync`, `stratz_client`, `sync_settings`; нет имён `VETMO_SYNC_SERVICE_KEY` / `VETMO_SYNC_STRATZ_TOKEN`; общий gateway не читает service-переменные; `vetmo.spec` не скрывает admin-модули |

Все тесты работают без сети и без реальных ключей: gateway и sync подменяются
фейками, секреты — временным файлом с фиктивными значениями.

### Существующие Admin-тесты
- `tests/admin/test_workers.py` — режимы `meta`/`full`/`dry`, сигналы `progress` /
  `finished` / `failed`, `trigger=admin-app`, `request_id`, кооперативная отмена.
- `tests/admin/test_ui_smoke.py` — создание окна, переключение 7 вкладок, отсутствие
  значений секретов в UI, фоновая загрузка меты/матчапов/истории/raw, проверки подключений.

---

## 3. Секреты в git (T-113, п. 1–2)

### 3.1. `git grep`

```powershell
git grep -n -I -E "VETMO_SYNC_SERVICE_KEY|service_role|VETMO_SYNC_STRATZ_TOKEN" -- . ':!docs/plans/*'
git grep -n -I -E "eyJ[A-Za-z0-9_-]{20,}|sb_secret_|sbp_[A-Za-z0-9]+" -- .
```

Результат:

- Совпадения по `service_role` / `VETMO_SYNC_*` есть **только** в:
  - коде и docstring Admin (`src/vetmo/admin/**`) — имена переменных и описание;
  - `src/vetmo/infra/sync_settings.py`, `src/vetmo/services/stratz_sync.py` — чтение
    секретов из `%APPDATA%`, без значений;
  - документации `docs/supabase-setup.md` — примеры вида `VETMO_SYNC_SERVICE_KEY=...`
    без реальных значений;
  - SQL-миграции — `grant execute ... to service_role`;
  - тестах — проверка, что значения не попадают в UI.
- Поиск JWT/`sb_secret_`/`sbp_`-токенов по отслеживаемым файлам: **совпадений нет**.
- Файлы `.env`, `secrets.env`, `api.txt` в git **не отслеживаются**.

**Вывод:** утечек значений ключей в отслеживаемых файлах нет.

### 3.2. `.gitignore`

Добавлены шаблоны:

```gitignore
.env
.env.local
pop.txt
secrets.env
api.txt
n8n_api_key.txt
*.n8n.key
n8n/.secrets
```

Проверка:

```powershell
git check-ignore -v api.txt n8n_api_key.txt foo.n8n.key n8n/.secrets .env secrets.env
```

Все шесть путей игнорируются (`.gitignore:17–24`). `api.txt` и планы n8n остались
неотслеживаемыми и в коммит не включены.

---

## 4. RLS Supabase (T-113, п. 3)

Скрипт-пробник читал `VETMO_SUPABASE_URL` и `VETMO_SUPABASE_ANON_KEY` из локального
`.env`; значения ключей не печатались и в отчёт не попали. `service_role`
**не использовался**.

| Запрос от `anon` | Ожидание | Факт | Вывод |
|---|---|---|---|
| `GET /rest/v1/vetmo_meta?limit=1` | 200 | **200**, 1 строка | чтение разрешено |
| `GET /rest/v1/vetmo_sync_runs?limit=1` | 200 | **200**, 1 строка | чтение разрешено |
| `POST /rest/v1/vetmo_sync_runs` (одна тестовая строка, `source=qa-rls-probe`) | 401/403 | **401**, код `42501`: `new row violates row-level security policy for table "vetmo_sync_runs"` | запись запрещена |

Строка при POST **не создана** — очистка БД не требуется.

**Вывод по RLS:** политика работает как задумано. В миграции
`20261020_001_init.sql` для всех `vetmo_*` включён RLS, политики `*_read`
дают `anon`/`authenticated` только `SELECT`; политик на запись для `anon` нет.
`service_role` обходит RLS и используется только Admin/sync-кодом.

---

## 5. Entry point пользователя (T-113, п. 4)

Проверены `src/vetmo/main.py` и `src/vetmo/ui/**` (AST-обход импортов в
`tests/admin/test_security.py`).

| Модуль | Импорты Admin/sync |
|---|---|
| `src/vetmo/main.py` | нет; только `PySide6`, `vetmo.ui.app_context`, `vetmo.ui.main_window`, `vetmo.ui.theme`, `vetmo.ui.app_icon` |
| `src/vetmo/ui/app_context.py` | нет `vetmo.admin`, `stratz_sync`, `stratz_client`, `sync_settings`; есть общий `vetmo.infra.supabase_gateway` |
| `src/vetmo/ui/**` (остальные) | запрещённых импортов нет |

**Замечание (архитектурное расхождение с текстом плана):** в §2 плана сказано,
что user exe не содержит `supabase_gateway`. Фактически `ui/app_context.py`
использует этот общий модуль, но создаёт его с **anon-ключом** и только для
чтения reference-данных; `service_role` в user-ветку не передаётся. Admin
передаёт service-ключ в тот же класс через `AdminContext`. Функционально
безопасно, но формально это deviation. Вариант на будущее — разделить
`ReadOnlyGateway` и `ServiceGateway` (T-114), чтобы совпадение с планом было
буквальным.

---

## 6. Проверка `VETMO.exe`

Текущий `dist/VETMO.exe` (сборка 2026-10-21 16:32) проверен побайтовым поиском
ASCII-строк:

```powershell
.\.venv\Scripts\python.exe -c "from pathlib import Path; b=Path('dist/VETMO.exe').read_bytes(); [print(s, s in b) for s in (b'service_role', b'stratz_sync', b'stratz_client', b'VETMO_SYNC_SERVICE_KEY', b'vetmo.admin')]"
```

Результат: все пять строк — `False`. `vetmo.spec` собирает только
`src/vetmo/main.py`, admin-модули не входят в граф импортов. Перед релизом
рекомендуется повторить проверку после пересборки в T-114.

---

## 7. Риски и замечания

| # | Риск / замечание | Серьёзность | Рекомендация |
|---|---|---|---|
| 1 | User-приложение импортирует общий `supabase_gateway` (в плане — не должен). Ключ только anon, запись reference-таблиц блокирует RLS | Низкая | Разделить gateway на read-only/service в T-114 либо зафиксировать решение в спеке |
| 2 | `api.txt` лежит в рабочей папке (теперь ignored, но не удалён) | Низкая | Проверить, не является ли файл рабочим ключом; удалить, если не нужен |
| 3 | Секреты Admin — в `%APPDATA%\VETMO\secrets.env`; при копировании папки/профиля ключ может уехать | Средняя | Не распространять Admin.exe; ограничить ACL; при подозрении ротировать `service_role` |
| 4 | `service_role` и STRATZ token читаются из env/файла в одном процессе Admin; компрометация ПК = компрометация записи | Средняя | Локальный PIN/шифрование файла секретов — опционально; не хранить secrets.env в OneDrive |
| 5 | Mypy: 10 ошибок в старых `test_ui_smoke.py` / `test_workers.py` (типизация фейков и `SimpleNamespace`), не в prod-коде | Низкая | Починить отдельной задачей, чтобы `mypy` был зелёным в финальном QA |
| 6 | В `vetmo_sync_runs` есть старый run со статусом `partial` и ошибкой про отсутствующий `delta_ban` (от 2026-10-20) | Низкая | Данные исторические; текущая схема `delta_ban` содержит. Можно удалить старые прогоны или оставить как историю |
| 7 | `vetmo_meta`/`vetmo_hero_matchups` полностью читаемы `anon` | Принято | Это reference-данные; запись запрещена RLS |

---

## 8. Воспроизводимость

```powershell
cd "C:\Users\pavel\OneDrive\Документы\Default Project"
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m pytest tests/admin -v --no-header
.\.venv\Scripts\python.exe -m ruff check tests/admin src/vetmo/admin
git grep -n -I -E "VETMO_SYNC_SERVICE_KEY|service_role|VETMO_SYNC_STRATZ_TOKEN" -- . ':!docs/plans/*'
git check-ignore -v api.txt n8n_api_key.txt foo.n8n.key n8n/.secrets .env secrets.env
```

RLS-пробник запускался отдельным временным скриптом (не коммитится), ключи
читались из `.env` и не выводились.
