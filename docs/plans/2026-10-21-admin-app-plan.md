# План: VETMO Admin — локальная программа обновления БД

**Дата:** 2026-10-21  
**Статус:** утверждён пользователем  
**Ветка:** `beta2`  
**Связанные документы:**
- `docs/plans/2026-10-19-vetmo-spec.md` — базовая спека приложения
- `docs/plans/2026-10-21-n8n-sync-plan.md` — архивный план GitHub Actions (не используется)

---

## 1. Цель

Сделать отдельную локальную программу **VETMO Admin** для пользователя-администратора, которая:

1. Ходит в STRATZ API с домашнего IP (Cloudflare пропускает).
2. Показывает техническую информацию: патч, мету, матчапы, баны, сырые ответы API, историю запусков.
3. **Единственная** пишет в Supabase (через `service_role`).
4. Позволяет запускать sync вручную: meta, full (с матчапами), dry-run.
5. Не требует GitHub Actions, n8n, VPS, прокси и платных сервисов.

Пользовательское приложение **VETMO** остаётся read-only: читает Supabase через `anon`-ключ и не может писать в БД.

---

## 2. Архитектура

```
┌─────────────────────────────────────────────┐
│  VETMO Admin.exe  (только у администратора) │
│                                             │
│  STRATZ API (curl_cffi, домашний IP)        │
│        ↓                                    │
│  агрегация (stratz_aggregate)               │
│        ↓                                    │
│  SupabaseGateway (service_role) → запись    │
│                                             │
│  UI: обзор, sync, мета, матчапы, raw, логи  │
└──────────────────┬──────────────────────────┘
                   │ запись
                   ▼
              ┌──────────┐
              │ Supabase │
              └────┬─────┘
                   │ чтение (anon key, RLS SELECT)
                   ▼
┌─────────────────────────────────────────────┐
│  VETMO.exe  (у пользователей)               │
│  Только просмотр; кнопка «Обновить из БД»   │
└─────────────────────────────────────────────┘
```

### Принципы
- **Один источник записи:** только Admin-программа.
- **Секреты не в git и не в exe:** `service_role` и STRATZ token — в `%APPDATA%\VETMO\secrets.env` (вне OneDrive).
- **Пользовательский exe не содержит** модулей `vetmo.admin`, `stratz_client`, `stratz_sync`, `supabase_gateway` (service writer).
- **RLS:** `anon` — только SELECT; `service_role` обходит RLS.
- **Никаких внешних оркестраторов:** n8n/GitHub Actions не участвуют в обновлении.

---

## 3. Ветки

| Ветка | Содержимое | Назначение |
|---|---|---|
| `release/beta` | Пользовательское приложение VETMO | Read-only, релиз для пользователей |
| `beta2` | Admin-приложение + sync-код | Локальное обновление БД |
| `runner` | Архив GitHub Actions-варианта | Можно удалить или оставить как историю |

`beta2` создаётся от `release/beta`, затем в неё мержится `runner` (улучшения sync: `trigger`, `request_id`, proxy). GitHub Actions workflow из `beta2` удаляется.

---

## 4. Структура кода (ветка `beta2`)

```
src/vetmo/
  admin/
    __init__.py
    main.py              # точка входа QApplication + AdminWindow
    context.py           # AdminContext: SyncSettings, StratzClient, SupabaseGateway
    window.py            # главное окно: сайдбар + QStackedWidget
    tabs/
      dashboard.py       # обзор, статус, кнопки
      sync_tab.py        # запуск sync, прогресс, лог
      meta_tab.py        # таблица меты с фильтрами
      matchups_tab.py    # матчапы по герою
      raw_tab.py         # сырые ответы STRATZ
      runs_tab.py        # история vetmo_sync_runs
      settings_tab.py    # проверка подключений, секреты
    workers.py           # QThread-обёртка над sync_all()
  services/
    stratz_client.py     # уже есть (curl_cffi)
    stratz_sync.py       # уже есть (sync_all)
    stratz_aggregate.py  # уже есть
  infra/
    supabase_gateway.py  # уже есть (service_role writer)
    sync_settings.py     # уже есть (secrets.env)
  domain/
    rank_brackets.py     # уже есть
```

Пользовательское приложение (`src/vetmo/main.py`, `src/vetmo/ui/`) не меняется, кроме кнопки обновления из БД.

---

## 5. Интерфейс Admin-программы

Средний по сложности PySide6-интерфейс: слева сайдбар с разделами, справа — контент.

### 5.1. Обзор
- Текущий патч (id, name).
- Последний запуск: статус, время, `rows_meta`, `rows_matchups`, `period_end`.
- Кнопки: **Обновить мету**, **Полный sync (с матчапами)**, **Dry-run**.
- Индикатор здоровья: свежесть данных, число ошибок.

### 5.2. Синхронизация
- Выбор режима: meta / full / dry-run.
- Прогресс-бар и текстовый лог в реальном времени.
- Кнопка «Отменить» (кооперативная отмена через флаг).
- После завершения — итог: patch, rows_meta, rows_matchups, errors.

### 5.3. Мета
- Фильтры: ранг (`0..8`), позиция (`0..5`), поиск по имени героя.
- Таблица: герой, winrate, pickrate, banrate, матчи, дельты.
- Сортировка по колонкам.
- Источник: `vetmo_meta` (свежий патч, `window_days=7`).

### 5.4. Матчапы
- Выбор героя.
- Три блока: контрпики (top-10), хорошие пики (top-10), связки (top-10).
- Winrate и число матчей, пометка «малая выборка» при необходимости.
- Источник: `vetmo_hero_matchups`.

### 5.5. Сырые данные STRATZ
- Выбор запроса: `gameVersions`, `winDay` (ранг/позиция), `banDay`, `matchUp` (герой/брекет).
- Кнопка «Выполнить».
- JSON-viewer с подсветкой/сворачиванием.
- Показывает HTTP-статус и время ответа.

### 5.6. История запусков
- Таблица `vetmo_sync_runs`: дата, статус, trigger, patch, rows_meta, rows_matchups, ошибка.
- Детали выбранного запуска: `details.slices`, `period_end`, `errors`.

### 5.7. Настройки
- Путь к `secrets.env`, статус наличия ключей (маскировано).
- Кнопки «Проверить Supabase» и «Проверить STRATZ».
- Отображение URL Supabase и STRATZ (без ключей).
- Кнопка «Открыть папку с секретами».

---

## 6. Безопасность

| Угроза | Мера |
|---|---|
| `service_role` в git | Файл `secrets.env` вне репозитория; `.gitignore`; проверка `git grep` |
| `service_role` в exe | Ключ читается только из `%APPDATA%`; в код не вшивается |
| Admin.exe у постороннего | Не распространять; опционально локальный PIN при запуске |
| Пользователь пишет в БД | В пользовательском exe нет `SupabaseGateway` и `service_role`; RLS запрещает запись для `anon` |
| Случайная перезапись матчапов | Запись только при 5/5 успешных брекетов (уже реализовано) |
| Утечка в логах | Ключи не логируются; в логах только статусы и имена |

RLS-политики (уже в миграциях):
- `anon` — SELECT на `vetmo_*`.
- `service_role` — полный доступ.

---

## 7. Задачи

### T-101. Создать ветку `beta2` и перенести sync-код
- **Агент:** backend-agent
- **Файлы:** ветка, `.github/workflows/stratz-sync.yml` (удалить), `tools/probe_stratz.py` (оставить)
- **Шаги:**
  - [ ] Создать `beta2` от `release/beta`.
  - [ ] Merge `runner` в `beta2`.
  - [ ] Удалить `.github/workflows/stratz-sync.yml` (GitHub Actions больше не нужен).
  - [ ] Убедиться, что `tools/sync_stratz.py`, `src/vetmo/services/stratz_*.py`, `src/vetmo/infra/supabase_gateway.py`, `sync_settings.py` на месте.
  - [ ] Коммит `chore(beta2): start admin app branch`.
- **Приёмка:** `git branch` содержит `beta2`; `python -m pytest` не сломан.

### T-102. Backend: AdminContext и SyncRunner
- **Агент:** backend-agent
- **Файлы:** `src/vetmo/admin/context.py`, `src/vetmo/admin/workers.py`
- **Шаги:**
  - [ ] `AdminContext`: `SyncSettings.load()`, `StratzClient`, `SupabaseGateway`, пути, версия.
  - [ ] `SyncRunner(QThread)`: принимает режим (`meta`/`full`/`dry-run`), вызывает `sync_all()` с `progress`-callback, испускает сигналы `progress(str)`, `finished(dict)`, `failed(str)`.
  - [ ] Флаг отмены: `cancel()`; `sync_all` проверяет его между срезами (добавить необязательный `should_stop`).
  - [ ] Тесты: `tests/admin/test_workers.py` (мок `sync_all`).
- **Приёмка:** тесты проходят; UI может запускать sync без блокировки.

### T-103. GUI: каркас Admin-окна
- **Агент:** gui-agent
- **Файлы:** `src/vetmo/admin/main.py`, `window.py`, `tabs/__init__.py`
- **Шаги:**
  - [ ] `QApplication`, тема `theme_for`, название «VETMO Admin».
  - [ ] Сайдбар: Обзор, Синхронизация, Мета, Матчапы, Сырые данные, История, Настройки.
  - [ ] `QStackedWidget` с заглушками вкладок.
  - [ ] Закрытие: корректно останавливать worker.
- **Приёмка:** приложение запускается, вкладки переключаются.

### T-104. GUI: вкладка «Обзор»
- **Агент:** gui-agent
- **Файлы:** `src/vetmo/admin/tabs/dashboard.py`
- **Шаги:**
  - [ ] Карточки: патч, последний run, rows_meta, rows_matchups, period_end.
  - [ ] Кнопки запуска sync с подтверждением.
  - [ ] Обновление данных после завершения sync.
- **Приёмка:** данные читаются из Supabase, кнопки работают.

### T-105. GUI: вкладка «Синхронизация»
- **Агент:** gui-agent
- **Файлы:** `src/vetmo/admin/tabs/sync_tab.py`
- **Шаги:**
  - [ ] Выбор режима, кнопка «Запустить», «Отменить».
  - [ ] Прогресс-бар + лог.
  - [ ] Сигналы от `SyncRunner`.
- **Приёмка:** sync запускается, лог обновляется, UI не зависает.

### T-106. GUI: вкладка «Мета»
- **Агент:** gui-agent
- **Файлы:** `src/vetmo/admin/tabs/meta_tab.py`
- **Шаги:**
  - [ ] Фильтры: ранг, позиция, поиск.
  - [ ] `QTableView` с моделью из `vetmo_meta`.
  - [ ] Сортировка, подсветка winrate.
- **Приёмка:** фильтры работают, данные соответствуют БД.

### T-107. GUI: вкладка «Матчапы»
- **Агент:** gui-agent
- **Файлы:** `src/vetmo/admin/tabs/matchups_tab.py`
- **Шаги:**
  - [ ] Выбор героя.
  - [ ] Три таблицы/списка: counter, good, synergy.
  - [ ] Пометка малой выборки.
- **Приёмка:** данные читаются из `vetmo_hero_matchups`.

### T-108. GUI: вкладка «Сырые данные STRATZ»
- **Агент:** gui-agent
- **Файлы:** `src/vetmo/admin/tabs/raw_tab.py`
- **Шаги:**
  - [ ] Выбор запроса и параметров.
  - [ ] Выполнение через `StratzClient`.
  - [ ] JSON-viewer, статус, время.
- **Приёмка:** запросы выполняются, JSON отображается.

### T-109. GUI: вкладка «История запусков»
- **Агент:** gui-agent
- **Файлы:** `src/vetmo/admin/tabs/runs_tab.py`
- **Шаги:**
  - [ ] Таблица `vetmo_sync_runs`.
  - [ ] Детали выбранного run.
- **Приёмка:** история отображается.

### T-110. GUI: вкладка «Настройки»
- **Агент:** gui-agent
- **Файлы:** `src/vetmo/admin/tabs/settings_tab.py`
- **Шаги:**
  - [ ] Статус ключей (маскировано).
  - [ ] Проверка Supabase/STRATZ.
  - [ ] Открыть папку с секретами.
- **Приёмка:** проверки работают, ключи не отображаются.

### T-111. Пользовательское приложение: кнопка «Обновить из БД»
- **Агент:** gui-agent
- **Файлы:** `src/vetmo/ui/main_window.py`, `src/vetmo/services/supabase_meta.py` (при необходимости)
- **Шаги:**
  - [ ] Кнопка/пункт меню «Обновить из БД».
  - [ ] Повторная загрузка меты/матчапов через `anon`.
  - [ ] Без каких-либо записей в БД.
- **Приёмка:** данные обновляются, запись не происходит.

### T-112. Тесты
- **Агент:** qa-agent
- **Файлы:** `tests/admin/`
- **Шаги:**
  - [ ] `test_workers.py` — сигналы, отмена.
  - [ ] `test_context.py` — загрузка секретов, отсутствие ключей.
  - [ ] `test_ui_smoke.py` — окно создаётся, вкладки переключаются.
  - [ ] `test_no_service_role_in_user_exe.py` — проверка сборки.
- **Приёмка:** `pytest` зелёный.

### T-113. QA безопасности
- **Агент:** qa-agent
- **Шаги:**
  - [ ] `git grep` по `service_role`, `VETMO_SYNC_SERVICE_KEY` — пусто в отслеживаемых файлах.
  - [ ] Проверить RLS: `anon` не может INSERT/UPDATE/DELETE.
  - [ ] Проверить, что `VETMO.exe` не содержит строк `service_role`/`stratz_sync`.
- **Приёмка:** отчёт `docs/qa-admin-security.md`.

### T-114. Упаковка
- **Агент:** packaging-agent
- **Файлы:** `vetmo.spec`, `vetmo-admin.spec`
- **Шаги:**
  - [ ] `VETMO-Admin.exe` — entry point `vetmo.admin.main`.
  - [ ] `VETMO.exe` — без admin/sync-модулей.
  - [ ] Проверить запуск обоих exe.
- **Приёмка:** оба exe собираются и запускаются; секретов внутри нет.

---

## 8. Критерии готовности

- [ ] Ветка `beta2` создана, sync-код работает.
- [ ] Admin-программа запускается, все вкладки доступны.
- [ ] Sync meta/full/dry-run запускается из UI, прогресс и лог отображаются.
- [ ] Мета, матчапы, история и сырые данные STRATZ отображаются.
- [ ] Пользовательское приложение читает БД и не пишет.
- [ ] `VETMO-Admin.exe` собран, `VETMO.exe` не содержит admin-кода и `service_role`.
- [ ] `git grep` по секретам пуст.
- [ ] Тесты проходят.

---

## 9. Риски

| Риск | Мера |
|---|---|
| ПК выключен — sync не идёт | Это ожидаемо; можно добавить Task Scheduler позже |
| Cloudflare заблокирует домашний IP | Сейчас локально `200`; при блокировке — VPN/прокси, но это отдельный шаг |
| Секреты в `%APPDATA%` | Не коммитить, не передавать; при утечке ротировать ключи |
| Ветка `beta2` расходится с `release/beta` | Общий код в `services`/`domain`; периодический merge |
| Случайная запись в БД из user-приложения | В user exe нет `SupabaseGateway`; RLS |
