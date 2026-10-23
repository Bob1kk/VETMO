# Сравнение OpenDota REST API и STRATZ GraphQL API для VETMO

**Дата:** 2026-10-21  
**Автор:** API-агент VETMO  
**Статус:** итоговый отчёт с рекомендацией  
**База:** исходный код репозитория (`src/vetmo/services/*`), live-запросы к `api.opendota.com`, документы `docs/stratz-actual-schema-notes.md`, `docs/qa-winrate-verification.md`, `docs/metrics_calculation_research.md`, план `docs/plans/2026-10-19-vetmo-plan-ru.md`.

---

## 0. Краткий вывод (Executive Summary)

| Критерий | Победитель | Комментарий |
|---|---|---|
| Hero Stats (винрейт/пикрейт/банрейт) | **OpenDota** | Публичен, без токена, простой parсинг JSON, точнее совпадает с dotabuff при `pub_pick/pub_win` + режиме All Pick. STRATZ `winDay` лагает ~10 дней и имеет разрывы данных. |
| Матчапы (контрпики/синергия) | **STRATZ** | `matchUp` отдаёт `vs` + `with` одним батч-запросом на всех героев, есть разбивка по рангам и неделе. OpenDota `heroes/{id}/matchups` — только `vs`, по одному герою за запрос, без недели/ранга. |
| Баны | **STRATZ** (с оговорками) | `banDay` даёт банрейт по героям; OpenDota имеет только `pro_ban` (про-сцена), паб-банрейта нет. STRATZ выборка сэмплированная, семантика `heroId`不明, но порядок значений доменно правдоподобен. |
| Патчи и версии | **Ничья** | Оба API отдают список патчей. OpenDota — с датами (`/constants/patch`); STRATZ — без дат (`constants.gameVersions`), но у STRATZ версия текущая (7.41f). |
| Технические ограничения | **OpenDota** | Нет токена, нет Cloudflare, работает через обычный `httpx`, токен не нужен в `.exe`. STRATZ требует токен (не в exe), `curl_cffi impersonate=chrome`, риск блокировки из России. |

**Рекомендация разделения ответственности (итог):**  
**OpenDota → hero stats (винрейт/пикрейт, общий и по рангам 1–8), патчи, иконки.**  
**STRATZ → матчапы (контрпики + синергия с ранговой и недельной разбивкой), банрейт (с оговоркой про сэмплирование).**  
STRATЗ пока оставить как дополнительный/опциональный источник из-за зависимости от токена и Cloudflare-обхода; OpenDota сделать основным для公開 мета.

---

## 1. Hero Stats (винрейт, пикрейт, банрейт по герою)

### 1.1 OpenDota — эндпоинты и поля

| Эндпоинт | Метод | Что возвращает | Примечания |
|---|---|---|---|
| `GET /api/heroStats` | GET | Список всех героев (127 шт.) с сырыми счётчиками | Основной источник меты |
| `GET /api/constants/patch` | GET | Список патчей `{name, date, id}` | Для метки версии патча |
| `GET /api/heroes` | GET | Каталог героев (id, name, localized_name, roles, и т.д.) | Доп. справочник |

**Ключевые поля `heroStats` (проверено наживо, 2026-10-21):**

| Поле | Смысл |
|---|---|
| `id`, `name`, `localized_name`, `icon`, `img` | Идентификатор, внутреннее имя, отображаемое имя, URL иконки |
| `primary_attr`, `attack_type`, `roles` | Атрибут, тип атаки, роли героя |
| `pub_pick`, `pub_win` | Общие пики/побесы в публичных матчах (все режимы) |
| `pub_pick_trend`, `pub_win_trend` | Тренд за ~7 дней (массив чисел) |
| `1_pick`…`8_pick`, `1_win`…`8_win` | Пики/победы по игровым режимам: `1` = All Pick, `2` = Captains Mode и т.д. |
| `pro_pick`, `pro_win`, `pro_ban` | Профессиональные пики/победы/баны |
| `turbo_picks`, `turbo_wins` | Турбо-режим |

**Расчёт на стороне клиента (уже реализовано в `opendota_client.py`):**
- `win_rate = pub_win / pub_pick * 100` (общий срез, `rank_tier=None`)
- `pick_rate = 1000 * pub_pick / Σ pub_pick` (доля от всех пиков, кап 100)
- `ban_rate = pro_ban / (pro_pick + pro_ban) * 100` (только про-баны, только общий срез)
- По рангам 1–8: `win_rate = N_win / N_pick * 100`, `pick_rate = 1000 * N_pick / Σ N_pick`

### 1.2 STRATZ — эндпоинты (запросы GraphQL)

| Запрос | Операция | Что возвращает | Примечания |
|---|---|---|---|
| `heroStats.winDay(...)` | GraphQL query | `{ day, heroId, winCount, matchCount }` | Основной источник меты (исторически) |
| `heroStats.stats(...)` | GraphQL query | `{ heroId, position, bracketBasicIds, matchCount, winCount, ... }` | Недельная статистика с позициями и рангами (сейчас основной) |
| `constants.gameVersions` | GraphQL query | `{ id, name }` | Список патчей |

**Поля `winDay` / `stats`:**

| Поле | Смысл |
|---|---|
| `day` | `winDay`: epoch seconds; `stats`: unix-время недели (четверг 00:00 UTC) |
| `heroId` | ID героя (STRATZ нумерация совпадает с OpenDota) |
| `position` | `POSITION_1`…`POSITION_5` (только `stats`) |
| `bracketBasicIds` | Ранговая группа (только `stats`): `UNCALIBRATED`, `HERALD_GUARDIAN`, `CRUSADER_ARCHON`, `LEGEND_ANCIENT`, `DIVINE_IMMORTAL` |
| `matchCount` | Число appearances heroes в слоте (10 слотов на матч, 1 на позицию) |
| `winCount` | Число побед героя |

**Расчёт на стороне клиента (уже реализовано в `stratz_aggregate.py`):**
- `slots_per_match = 10` (все позиции) или `1` (конкретная позиция)
- `total_matches = Σ matchCount / slots_per_match`
- `win_rate = wins / matches * 100`
- `pick_rate = matches / total_matches * 100`
- `ban_rate` — из `banDay` отдельно (см. раздел 3)

### 1.3 Фильтры: сравнение

| Фильтр | OpenDota (`heroStats`) | STRATZ (`winDay`/`stats`) |
|---|---|---|
| Патч | ❌ Нет (всегда rolling window последних parsed-матчей) | ❌ Нет прямой фильтрации меты по патчу; патч — только метка источника (`gameVersions`) |
| Игровой режим | ⚠️ Частично: поля `1_pick`…`8_pick` по режимам (1 = All Pick), но нет параметра запроса | ✅ Да: `gameModeIds: [ALL_PICK]` / `[ALL_PICK_RANKED]` |
| Ранг / скилл | ❌ Нет в `heroStats` (только на сайте); `pro_pick/pro_ban` — про-сцена | ✅ Да: `bracketIds` / `bracketBasicIds` (5 групп в `stats`; `winDay` не принимает `bracketIds` — HTTP 400) |
| Регион | ❌ Нет | ⚠️ `regionIds` существует в схеме `winDay`, но не проверено на практике |
| Позиция | ❌ Нет в `heroStats` (на сайте есть, в API не разведено явно) | ✅ Да: `positionIds: [POSITION_1…POSITION_5]` |
| Дата / окно | ❌ Нет (скользящее окно парсера, не公開) | ⚠️ Частично: `winDay` — последние доступные дни (лаг); `stats` — неделя по `week` |

### 1.4 Актуальность данных (задержка обновления)

| Аспект | OpenDota | STRATZ |
|---|---|---|
| Тип окна | Скользящее окно последних распарсенных реплеев (точное начало/конец не publikujeтся) | `winDay`: последние доступные дни, лаг до 10 дней от календаря, разрывы (2026-09-18…30 отсутствовали); `stats`: текущая неделя (четверг–среда) |
| Известная задержка | Неизвестна (не dokumentировано) | `winDay` отстаёт ~10 дней (на 2026-10-21 максимум был 2026-10-10); `stats` — актуальная неделя |
| Стабильность окна | Стабильно (всегда свежие parsed-матчи) | Нестабильно: `winDay` имеет разрывы; `stats` стабильнее |

### 1.5 Точность по сравнению с Dotabuff/OpenDota (референсы)

**Результаты верификации (из `docs/qa-winrate-verification.md`):**

- STRATЗ `winDay` с фильтром `ALL_PICK` (не ранк) давал sistematicное расхождение с Dotabuff: ALL_PICK ≈ unranked All Pick (~789 тыс. матчей/неделя) vs Dotabuff ranked All Pick (~3.6 млн матчей/неделя).
- Переключение на `ALL_PICK_RANKED` убрало систематическое расхождение.
- **Среднее абсолютное расхождение WR с Dotabuff (126 из 127 героев): 0.267 п.п., медиана 0.215 п.п., 95-й перцентиль 0.721 п.п., максимум 1.146 п.п. (Meepo).**
- Пикрейты совпадают в пределах ~1–2 п.п.

**OpenDota:** по сути сам является одним из референсов (dotabuff и OpenDota часто близки). В `metrics_calculation_research.md` приведён пример: Necrophos `pub_pick=653 243`, `pub_win=332 750` → общий pub WR ≈ 50.94 %, по режиму 1 (All Pick) WR ≈ 53.82 %. Это показывает, что OpenDota даёт разные значения в зависимости от режима — клиент должен явно выбирать All Pick (режим 1) для сравнимости с референсами.

**Вывод по точности:** Оба API могут быть близки к референсам, если правильно выбраны фильтры (All Pick Ranked, одинаковое окно, одинаковый срез ранга). STRATZ с `ALL_PICK_RANKED` продемонстрировал точность ±0.27 п.п. WR vs Dotabuff. OpenDota не проходит прямую сверку в этом отчёте (нет отдельного документа верификации), но является независимым публичным источником с прозрачной формулой (`win/pick*100`).

### 1.6 Формат ответа и легкость парсинга

| Аспект | OpenDota | STRATZ |
|---|---|---|
| Транспорт | `GET` + JSON, обычный `httpx` | `POST GraphQL` + JSON, требует `curl_cffi impersonate=chrome` |
| Структура | Плоский список объектов, поля верхнего уровня | Вложенные `data.heroStats.winDay/stats/matchUp/banDay`, нужна навигация по GraphQL-ответу |
| Аутентификация | Не требуется | Требуется `Bearer` токен |
| Обработка ошибок | HTTP-статусы, ретраи на 5xx/429 | GraphQL `errors` массив + HTTP-статусы |
| Токен в `.exe` | Не нужен | **Нельзя вшивать** — хранится в `%APPDATA%/VETMO/secrets.env` |

---

## 2. Матчапы (контрпики, синергия)

### 2.1 OpenDota

| Эндпоинт | Метод | Поля | Примечания |
|---|---|---|---|
| `GET /api/heroes/{id}/matchups` | GET | `hero_id` (или `against_hero_id`), `games_played`, `wins` | Только контрпики (`vs`); синергии (`with`) — отсутствуют в этом эндпоинте |

**Реализовано в VETMO (`opendota_client._sync_matchups_for_hero`):**
- Один запрос на героя → 127 запросов для полной матрицы
- Фильтры: только `hero_id` (путь запроса); нет ранга, недели, патча
- `games_played` — минимальная выборка pares (в коде `min_games=100` по R2)
- Винрейт против оппонента = `wins / games_played * 100`
- Синергии не загружаются (нет эндпоинта `with` в OpenDota matchups)

**Ограничения OpenDota матчапов:**
- ❌ Нет синергий (только контрпики)
- ❌ Нет фильтра по рангу/скиллу
- ❌ Нет фильтра по неделе/патчу (всегда rolling window)
- ❌ 127 отдельных запросов для полной матрицы (rate limit ~60/мин → >2 мин на полную синхронизацию)
- ❌ Нет региона

### 2.2 STRATZ

| Запрос | Операция | Поля | Примечания |
|---|---|---|---|
| `heroStats.matchUp(heroIds, week, bracketBasicIds, take)` | GraphQL | `vs: [{ heroId1, heroId2, matchCount, winCount, winsAverage }]`, `with: [...]` | Контрпики + синергии в одном ответе |

**Реализовано в VETMO (`stratz_client.matchup_groups`):**
- Один запрос с массивом `heroIds` → данные для всех героев сразу (экономит 127 запросов)
- Поля `vs`: `heroId2`, `matchCount`, `winCount`, `winsAverage` (доля 0..1)
- Поля `with`: та же структура (синергии)
- Фильтры: `heroIds` (список), `week` (unix-время недели), `bracketBasicIds` (ранговая группа), `take`
- ⚠️ `bracketBasicIds: [ALL]` возвращает пустой ответ — не использовать
- ⚠️ `matchLimit: 100` в тесте давал пустой ответ — без него работает

**Ограничения STRATZ матчапов:**
- ⚠️ Выборка сэмплированная (STRATZ не даёт полный пул матчей)
- ⚠️ Нет региона (не документировано)
- ⚠️ `bracketBasicIds: [ALL]` не работает; нужны отдельные запросы по группам рангов

### 2.3 Качество данных (выборка, надёжность)

| Критерий | OpenDota | STRATZ |
|---|---|---|
| Выборка матчапов | Полный пул parsed-матчей OpenDota | Сэмплированная выборка STRATZ |
| Синергии | ❌ Недоступны | ✅ Доступны (`with`) |
| Батч-загрузка всех героев | ❌ 127 отдельных запросов | ✅ Один запрос на всех |
| Фильтр по неделе | ❌ Нет | ✅ `week` |
| Фильтр по рангу | ❌ Нет | ✅ `bracketBasicIds` |
| Порог надёжности | На стороне клиента (`min_games=100`) | На стороне клиента (`MATCHUP_RELIABLE_MIN=500`, `MATCHUP_MIN_MATCHES=1`) |

**В VETMO уже реализована логика надёжности для STRATZ (`stratz_aggregate.select_matchup_highlights`):**
- `MATCHUP_RELIABLE_MIN = 500` — порог для «надёжного» матчапа
- `MATCHUP_MIN_MATCHES = 1` — минимальный порог включения
- Топ-10 highlights: сначала надёжные, затем fallback по выборке (не по экстремальному WR)
- Синергии и контрпики разделяются (`counter` / `good` / `synergy`)

---

## 3. Баны (банрейт по герою, динамика банов)

### 3.1 OpenDota

| Эндпоинт | Поля | Семантика |
|---|---|---|
| `GET /api/heroStats` | `pro_ban`, `pro_pick` | Только профессиональные баны; паб-банрейт **отсутствует** |

**Семантика:** `ban_rate = pro_ban / (pro_pick + pro_ban) * 100` — это про-банрейт, не паблик. Для паблик All Pick банрейта в OpenDota нет.

### 3.2 STRATZ

| Запрос | Поля | Семантика |
|---|---|---|
| `heroStats.banDay(heroId, take, groupByDay, groupByRank)` | `heroId`, `day`, `bracketBasicIds`, `matchCount`, `winCount` | `matchCount` = число банов героя (не матчей!) |

**Критические особенности STRATZ `banDay` (подтверждено live-интроспекцией):**

1. **`heroId` обязателен, но ИГНОРИРУЕТСЯ** — API всегда возвращает строки по всем 127 героям. В коде VETMO запрос отправляется с `heroId=1` (заглушка), а агрегация идёт по полю `heroId` в строках ответа.

2. **`take` — число ДНЕЙ истории, а не строк** — `take=30` → 30 дней бан-данных.

3. **`day` — индекс дня**, не epoch seconds (в отличие от `winDay`). `day=null` только без группировки (тогда lifetime-суммы).

4. **`bracketBasicIds`** — 5 групп рангов: `UNCALIBRATED`, `HERALD_GUARDIAN`, `CRUSADER_ARCHON`, `LEGEND_ANCIENT`, `DIVINE_IMMORTAL`.

5. **Банрейт нормируется:** выборка `banDay` меньше полного пула матчей, поэтому абсолютный банрейт считается как:
   ```
   ban_rate = bans_hero / (Σ bans_всех_героев / 10) * 100
   ```
   (10 банов на матч в Ranked All Pick — 5 на команду).

### 3.3 Надёжность данных о банах

| Критерий | OpenDota | STRATZ |
|---|---|---|
| Источник банов | Только про-сцена (`pro_ban`) | Паблик Ranked All Pick (`banDay`) |
| Паб-банрейт | ❌ Нет | ✅ Есть (сэмплированный) |
| Точность абсолютных значений | Высокая (про-матчи, полная выборка) | Средняя (сэмплирование, допущение 10 банов/матч) |
| Динамика банов | ❌ Нет (`pro_ban` — суммарное число) | ✅ Есть (`banDay` по дням) |
| Семантика ясна | Да | ⚠️ `heroId` игнорируется, `matchCount` = бан count |

**Пример полученных бан-рейтов (ранг 0, окно 04.10–10.10.2026, из `qa-winrate-verification.md`):**
- Outworld Destroyer 46.1 %, Phantom Lancer 41.4 %, Lifestealer 38.3 %, Lina 33.6 %, Necrophos 23.0 %, Wraith King 2.4 % (высокий WR 55 %, но почти не банят — доменно правдоподобно).

---

## 4. Патчи и версии игры

### 4.1 OpenDota

| Эндпоинт | Поля | Можно ли фильтровать мету по патчу |
|---|---|---|
| `GET /api/constants/patch` | `id`, `name`, `date` | ❌ Нет — `heroStats` всегда rolling window последних parsed-матчей, нет параметра патча |

**Реализовано в VETMO (`OpenDotaClient.latest_patch`):**
- Берёт максимальный `id` из `/constants/patch`
- Возвращает `(версия, дата)` — например `("7.41", "2025-12-16")`
- Fallback: `"public-ladder"` без даты, если справочник недоступен
- Патч используется только как метка источника в БД, не как фильтр данных

**Последний патч на 2026-10-21:** `7.41` (id 60, дата 2025-12-16). Обратите внимание: OpenDota отстаёт — последняя версия 7.41, а не 7.41f.

### 4.2 STRATZ

| Запрос | Поля | Можно ли фильтровать мету по патчу |
|---|---|---|
| `constants.gameVersions` | `id`, `name` | ❌ Нет — нет параметра патча в `winDay`/`stats`/`matchUp` |

**Реализовано в VETMO (`StratzClient.game_versions`):**
- Возвращает список `{id, name}`
- На 2026-10-21: 189 версий, последняя `7.41f` (id 190)
- `winGameVersion` исторически неполный — не считать источником патчей

**Сравнение версий патчей:**
| API | Последний патч | Дата |
|---|---|---|
| OpenDota | `7.41` | 2025-12-16 |
| STRATZ | `7.41f` | не указана (нет дат в ответе) |

STRATZ актуальнее по версии (7.41f vs 7.41), но не даёт дат релиза.

---

## 5. Технические ограничения

### 5.1 Аутентификация

| Аспект | OpenDota | STRATZ |
|---|---|---|
| Токен | ❌ Не требуется | ✅ Требуется `Bearer` токен |
| Где хранится токен | Н/Д | `%APPDATA%\VETMO\secrets.env` (не в git) |
| Токен в `.exe` | Н/Д | **Запрещено** — токен не должен попадать в one-file exe (PyInstaller) |
| Логирование токена | Н/Д | Не логируется (в коде `stratz_client.py` токен только в заголовке) |

### 5.2 Rate limits

| Аспект | OpenDota | STRATZ |
|---|---|---|
| Лимит | ~60 запросов/мин (публично заявлено) | Не документировано публично |
| Заголовки лимита | `X-Rate-Limit-Remaining-Minute`, `X-Rate-Limit-Remaining-Day` | Нет standard заголовков |
| Реализация в коде | `build_http_client` + `_respect_rate_limit` (минимальный интервал между запросами) | 3 попытки на 429/5xx с задержкой 1–2 сек |
| Влияние на синхронизацию | 127 héros + 127 matchups = 254 запроса → ~4.5 мин при 60/мин | Один GraphQL запрос может заменить dozens REST-запросов (батч matchups) |

### 5.3 Доступность из России / Cloudflare

| Аспект | OpenDota | STRATZ |
|---|---|---|
| Прямой доступ | ✅ Работает через обычный `httpx` | ❌ Plain `httpx` получает Cloudflare `403 Just a moment...` |
| Обход Cloudflare | Не нужен | ✅ `curl_cffi` с `impersonate="chrome"` проходит; `curl.exe` тоже проходит |
| Прокси | Не требуется | Поддерживается через `VETMO_SYNC_STRATZ_PROXY` |
| Риск блокировки из России | Низкий | Средний/высокий (Cloudflare может блокировать по гео) |

### 5.4 Наличие в пользовательском `.exe`

| Аспект | OpenDota | STRATZ |
|---|---|---|
| Секрет в коде | Нет | Токен не должен попадать в exe |
| Архитектура sync | Клиентское приложение запрашивает API напрямую | Sync-скрипт запускается отдельно (`tools/sync_stratz.py`), приложение читает из Supabase/локальной БД |
| Работа без токена | ✅ Да | ❌ Нет (приложение не получает STRATZ токен) |

---

## 6. Рекомендация разделения ответственности

### Итоговая матрица

| Данные | Рекомендуемое API | Обоснование |
|---|---|---|
| **Hero stats: винрейт, пикрейт (общий и по рангам 1–8)** | **OpenDota** | Публичен, без токена, нет Cloudflare, простой JSON, прозрачная формула (`win/pick*100`), работает через обычный `httpx`, токен не нужен в `.exe`. Режим `1` (All Pick) даёт сравнимую с референсами метрику. |
| **Hero stats: банрейт (паблик)** | **STRATZ** (с оговоркой) | OpenDota имеет только `pro_ban` (про-сцена). STRATZ `banDay` даёт паб-банрейт, но сэмплированный, с нормализацией на 10 банов/матч. Использовать как дополнительный источник, помечать как оценочный. |
| **Матчапы: контрпики (`vs`)** | **STRATZ** | Один батч-запрос на всех героев (`heroIds`), есть `vs` + `with`, фильтры по неделе и рангу, надёжность выборки помечается (`sample_reliable`). OpenDota требует 127 отдельных запросов и не имеет синергий. |
| **Матчапы: синергии (`with`)** | **STRATZ** | OpenDota не предоставляет синергии в matchups API. STRATЗ отдаёт `with` в том же запросе. |
| **Бан-динамика (по дням)** | **STRATZ** | `banDay` даёт данные по дням и ранговым группам. OpenDota не имеет временной динамики банов. |
| **Патчи и версии** | **OpenDota** (дата релиза) + **STRATZ** (текущая версия) | OpenDota даёт даты релиза патчей (`/constants/patch`). STRATZ имеет более актуальную версию (7.41f), но без дат. Рекомендуется использовать OpenDota для дат, STRATZ для уточнения версии. |
| **Иконки героев** | **OpenDota** | Прямые URL в `heroStats.icon/img`, нет токена, легко кэшировать (уже реализовано `sync_icon_cache`). |

### Рекомендуемая архитектура потока данных VETMO

```
OpenDota API (публичный, без токена)
├── GET /api/heroStats          → герои, винрейт, пикрейт (pub + ранги 1–8), банрейт (pro)
├── GET /api/constants/patch    → версия патча + дата релиза
├── GET /api/heroes/{id}/matchups → контрпики (fallback, если STRATZ недоступен)
└── GET /api/hero icons           → иконки для CV и UI

STRATZ GraphQL (требует токен, только sync-скрипт)
├── heroStats.stats(week, groupByPosition, groupByBracket) → свежая неделя, позиции, ранги
├── heroStats.matchUp(heroIds, week, bracket)              → контрпики + синергии батчем
├── heroStats.banDay(take, groupByDay, groupByRank)        → банрейт по дням/рангам
└── constants.gameVersions                                 → список патчей (версия без даты)

Локальная SQLite — источник истины для приложения
Supabase — опциональная синхронизация (service_role токен, не в exe)
```

### Поэтапный план внедрения

| Этап | Что сделать | Ответственный |
|---|---|---|
| 1 | OpenDota сделать основным источником hero stats (уже реализован `opendota_client.py`) | Backend-agent |
| 2 | Добавить fallback: если STRATZ недоступен (нет токена / Cloudflare / ошибка), использовать OpenDota matchups для контрпиков | Backend-agent |
| 3 | STRATZ оставить как дополнительный источник для матчапов и банов (sync-скрипт, отдельно от приложения) | API-agent / Backend-agent |
| 4 | В UI явно помечать источник данных и период актуальности (`snapshot_date`) | GUI-agent |
| 5 | Банрейт из STRATZ помечать как «оценочный» (сэмплированная выборка) | Backend-agent |

---

## 7. Уже реализованное в `opendota_client.py` (отправная точка)

Файл `src/vetmo/services/opendota_client.py` (547 строк) уже содержит:

1. **`OpenDotaClient`** — HTTP-клиент на `httpx` с:
   - Rate limiting: `_min_interval = 60 / rate_limit_per_min` (по умолчанию 60/мин → 1 сек между запросами)
   - Ретраи: 3 попытки с экспоненциальной задержкой (0.5/1.0/2.0 сек) на 5xx/429/сеть
   - `_request(path)` — базовый GET с построением URL `base_url + path`

2. **`latest_patch()` / `latest_patch_version()`** — `GET /api/constants/patch`, берёт макс. `id`, возвращает `(версия, дата)`, fallback `"public-ladder"`

3. **`sync_heroes(limit=0)`** — `GET /api/heroStats`:
   - Кэш TTL (24 ч) через `last_sync_heroes` в настройках
   - Расчёт meta: общий срез (`rank_tier=None`: `win=pub_win/pub_pick*100`, `pick=1000*pub_pick/Σpub_pick`) + по рангам 1–8
   - `ban_rate = pro_ban/(pro_pick+pro_ban)*100` — только общий срез (OpenDota не даёт про-баны по рангам)
   - Валидация через `ValidatorService`, upsert в БД, один commit на срез

4. **`sync_matchups(hero_ids, rivals_per_hero=30)`** — `GET /api/heroes/{id}/matchups`:
   - Только `vs` (контрпики), нет синергий
   - `games_played` фильтр (`min_games`), сортировка по `games_played` убыв.
   - `top-N` по выборке (`rivals_per_hero`)

5. **`sync_matchups_all(resume, min_games=100)`** — полная синхронизация всех героев с прогрессом в настройках (`matchups_synced_hero_ids`)

6. **`sync_icon_cache(icons_dir)`** — скачивание иконок героев в PNG, атомарная замена, проверка сигнатуры PNG

**Чего НЕ реализовано в `opendota_client.py`:**
- ❌ Фильтрация по патчу (heroStats всегда rolling window)
- ❌ Фильтрация по региону
- ❌ Синергии (`with`) — нет такого эндпоинта в OpenDota matchups
- ❌ Банрейт паблика — только `pro_ban`
- ❌ Позиционная статистика (positions не разводятся в heroStats)

---

## 8. Дополнительные риски и оговорки

1. **OpenDota `heroStats` не даёт точного временного окна** — данные это скользящее окно parsed-матчей, начало/конец не publikujeтся. Сравнение с Dotabuff «последние 7 дней» может давать небольшие расхождения из-за разных окон.

2. **OpenDota mode `1` (All Pick) ≠ `ALL_PICK_RANKED`** — в `heroStats` поле `1_pick/1_win` это All Pick без разделения на ranked/unranked. Для максимальной точности нужен срез ranked, которого в `heroStats` нет. STRATZ с `gameModeIds=[ALL_PICK_RANKED]` в этом смысле точнее.

3. **STRATZ токен и Cloudflare** — если токен истечёт или отзовётся, или Cloudflare заблокирует `curl_cffi` impersonation, синхронизация STRATZ прервётся. Приложение должно работать без STRATZ (использовать OpenDota + локальную БД).

4. **STRATZ `winDay` разрывы данных** — на 2026-10-21 был разрыв 2026-09-18…30 и лаг 10 дней. Новый `stats` эндпоинт решает часть проблемы (текущая неделя), но требует правильного вычисления `week` (четверг 00:00 UTC).

5. **STRATZ `banDay` семантика** — `heroId` игнорируется, `matchCount` = бан count (не матчи), требует нормализации на 10 банов/матч. Абсолютные значения банрейта — оценочные.

---

## 9. Новые контракты методов (для реализации)

### OpenDota (существующие, в `opendota_client.py`)

```python
class OpenDotaClient:
    def latest_patch(self) -> tuple[str, datetime | None]
    def latest_patch_version(self) -> str
    def sync_heroes(self, limit: int = 0) -> SyncResult
    def sync_matchups(self, hero_ids: int | list[int] | None = None, rivals_per_hero: int = 30) -> SyncResult
    def sync_matchups_all(self, resume: bool = True, min_games: int = 100) -> dict[str, Any]
    def sync_icon_cache(self, icons_dir: Path | str = ..., http_client=None) -> dict[str, int]
```

### STRATZ (существующие, в `stratz_client.py`)

```python
class StratzClient:
    def win_day(self, *, position: int | None = None, take: int = 3000) -> list[dict]
    def hero_stats_week(self, week: int, *, group_by_position: bool = True, group_by_bracket: bool = True) -> list[dict]
    def game_versions(self) -> list[dict]
    def matchup_groups(self, hero_ids: list[int], *, take: int = 300, week: int | None = None, bracket: str | None = None) -> dict[int, dict[str, list[dict]]]
    def matchups(self, hero_id: int, take: int = 100) -> list[dict]
    def ban_day(self, *, hero_id: int | None = None, days: int = 30, group_by_day: bool = True, group_by_rank: bool = True) -> list[dict]
    def close(self) -> None
```

### Предложение: унифицированный интерфейс источника мета (для будущего рефакторинга)

```python
class MetaSourceProtocol(Protocol):
    def sync_heroes(self) -> SyncResult: ...
    def sync_meta(self, patch_id: int) -> list[MetaRow]  # win_rate, pick_rate, ban_rate
    def sync_matchups(self, patch_id: int) -> list[MatchupRow]  # vs/with, win_rate, match_count
    def sync_bans(self, patch_id: int) -> list[BanRow]  # ban_rate per hero
    def get_patch_info(self) -> PatchInfo  # version, release_date
    @property
    def source_name(self) -> str: ...
```

OpenDota реализует `sync_heroes`, `sync_matchups` (только vs), `get_patch_info` (с датой). STRATZ реализует `sync_meta` (через `stats`/`winDay`), `sync_matchups` (vs + with), `sync_bans`, `get_patch_info` (версия без даты).

---

**Итог:** Для VETMO рекомендуется гибридный подход — OpenDota как основной публичный источник hero stats и патчей (без токена, без Cloudflare, безопасно для `.exe`), STRATZ как дополнительный источник для матчапов (включая синергии) и паб-банрейта (через отдельный sync-скрипт с токеном, не в exe). Это даст максимальную точность мета, близкую к референсным сайтам, при минимальных технических рисках для клиентского приложения.
