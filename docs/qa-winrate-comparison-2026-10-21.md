# Отчёт QA: верификация данных меты (OpenDota vs STRATZ vs референсы)

**Дата:** 2026-10-21  
**Ветка:** `beta2`  
**Репозиторий:** `C:\Users\pavel\OneDrive\Документы\Default Project`  
**Патч:** 7.41f  
**Режим:** All Pick Ranked  
**Ранги:** все (кроме另有 указано)  
**Источники:** OpenDota API (`/api/heroStats`), Dotabuff.com (страницы героев), STRATZ GraphQL (`winDay`), документация `docs/qa-winrate-verification.md`

---

## 1. Исходный код, проинспектированный

| Файл | Назначение | Ключевые выводы |
|------|-----------|-----------------|
| `src/vetmo/services/stratz_client.py` | STRATZ GraphQL-клиент | Использует `winDay` с `gameModeIds=[ALL_PICK_RANKED]`. `bracketIds` не передаётся (HTTP 400). Данные за все ранги (rank 0). `winDay` в октябре 2026 отставал на ~10 дней → переход на `stats(week)` и обратно к `winDay` (см. раздел 10 `qa-winrate-verification.md`). |
| `src/vetmo/services/opendota_client.py` | OpenDota REST-клиент | `GET /api/heroStats` — без ключа, rate-limit. WR = `pub_win/pub_pick*100`; pick_rate = `1000*pub_pick/Σpub_pick` (кап 100); ban_rate = `pro_ban/(pro_pick+pro_ban)*100` (только про-уровень, пишется в rank_tier=None). Валидатор карантит невалидные записи (T-007). |
| `src/vetmo/services/stratz_aggregate.py` | Агрегация STRATZ | `aggregate_win_day` считает WR=`winCount/matchCount*100`, pick_rate=`matchCount/total_matches*100` (слот = 10 для position=0, 1 для position>0). Баны нормируются: `bans_hero/(Σbans/10)*100` (10 банов на матч). |
| `docs/qa-winrate-verification.md` | QA отчёт сверки STRATZ→Dotabuff | STRATZ `winDay`+`ALL_PICK_RANKED` показывает среднее абсолютное расхождение WR **0.267 п.п.** vs Dotabuff. Медиана 0.215, 95-й пер센тиль 0.721. |
| `docs/qa-admin-security.md` | QA админ/безопасность | 206 тестов passed, ruff/mypy чисто. `.env` не в git. STRATZ токен хранится в `%APPDATA%\VETMO\secrets.env` (не в репозитории). |

---

## 2. Выбранные герои (10 популярных)

Phantom Lancer, Techies, Pudge, Lion, Rubick, Sniper, Juggernaut, Wraith King, Spectre, Necrophos.

---

## 3. Данные из OpenDota API (живой запрос `GET /api/heroStats`)

API доступен без ключа. Формулы соответствуют `opendota_client.py`:

- **WR** = `pub_win / pub_pick × 100`
- **Pick rate** = `min(100, 1000 × pub_pick / Σpub_pick)` (относительная доля, сумма ≈ 1000 ÷ 10 слотов)
- **Ban rate** = `min(100, pro_ban / (pro_pick + pro_ban) × 100)` — только про-уровень

| Герой | ID | OpenDota WR | OpenDota Pick | OpenDota Ban | pro_pick | pro_ban |
|-------|-----|-------------|---------------|--------------|----------|---------|
| Juggernaut | 8 | 52.57% | 18.01% | 55.56% | 4 | 5 |
| Phantom Lancer | 12 | 52.82% | 11.93% | 63.64% | 8 | 14 |
| Pudge | 14 | 51.39% | 27.26% | 13.79% | 25 | 4 |
| Lion | 26 | 48.72% | 24.44% | 50.00% | 5 | 5 |
| Sniper | 35 | 49.93% | 19.87% | 60.00% | 6 | 9 |
| Necrophos | 36 | 50.95% | 15.15% | 65.67% | 46 | 88 |
| Wraith King | 42 | 54.89% | 12.68% | 0.00% | 5 | 0 |
| Spectre | 67 | 53.26% | 9.68% | 0.00% | 4 | 0 |
| Rubick | 86 | 49.56% | 19.28% | 25.97% | 57 | 20 |
| Techies | 105 | 51.03% | 13.81% | 69.42% | 63 | 143 |

Источник: `https://api.opendota.com/api/heroStats` (живой запрос, 2026-10-21).  
Всего `pub_pick` по всем героям: 43,294,729.

---

## 4. Данные из Dotabuff.com (живой скрапинг страниц героев)

Dotabuff показывает раздел "This Week" (недельный срез, All Pick, все ранги). **Пикрейт и банрейт не отображаются как отдельные числа в основной карточке героя** — только в контексте фансетов (фрагментов страницы), поэтому в таблице ниже только WR и рейтинг популярности.

| Герой | Popularity (Dotabuff) | Dotabuff WR |
|-------|----------------------|-------------|
| Pudge | 1st | 51.37% |
| Lion | 2nd | 48.65% |
| Sniper | 3rd | 49.84% |
| Rubick | 4th | 49.54% |
| Juggernaut | 5th | 52.61% |
| Techies | 22nd | 51.07% |
| Necrophos | 17th | 50.89% |
| Phantom Lancer | 31st | 52.90% |
| Wraith King | 27th | 54.81% |
| Spectre | 39th | 53.28% |

Источник: `https://www.dotabuff.com/heroes/<slug>` (живой скрапинг, 2026-10-21, "Last Updated 2026-10-21").

---

## 5. STRATZ vs Dotabuff (из `docs/qa-winrate-verification.md`, ранее выполнено)

STRATЗ `winDay` + `ALL_PICK_RANKED`, patch 7.41f, rank 0:

| Герой | STRATZ WR | Dotabuff WR | Δ (STRATZ − DB) |
|-------|-----------|-------------|-----------------|
| Phantom Lancer | 53.25% | 53.22% | +0.03 |
| Wraith King | 55.08% | 54.90% | +0.18 |
| Pudge | 51.10% | 51.18% | −0.08 |
| Juggernaut | 52.88% | 52.59% | +0.29 |
| Necrophos | 50.87% | 50.70% | +0.17 |

Агрегированная статистика по 126 из 127 героев:
- Среднее абсолютное расхождение WR: **0.267 п.п.**
- Медиана: **0.215 п.п.**
- 95-й перцентиль: **0.721 п.п.**
- Максимум: **1.146 п.п.** (Meepo, пикрейт 1.6 %)

Пикрейты совпадают в пределах ~1–2 п.п. (WK 12.07 vs 12.88, Pudge 27.61 vs 28.25, PA 12.66 vs 12.75).

---

## 6. OpenDota vs Dotabuff (мои жирые данные)

| Герой | OpenDota WR | Dotabuff WR | Δ (OD − DB) | OpenDota Pick | Dotabuff Popularity | OpenDota Ban | Dotabuff Ban |
|-------|-------------|-------------|-------------|---------------|---------------------|--------------|--------------|
| Juggernaut | 52.57% | 52.61% | −0.04 | 18.01% | 5th | 55.56% | — |
| Phantom Lancer | 52.82% | 52.90% | −0.08 | 11.93% | 31st | 63.64% | — |
| Pudge | 51.39% | 51.37% | +0.02 | 27.26% | 1st | 13.79% | — |
| Lion | 48.72% | 48.65% | +0.07 | 24.44% | 2nd | 50.00% | — |
| Sniper | 49.93% | 49.84% | +0.09 | 19.87% | 3rd | 60.00% | — |
| Necrophos | 50.95% | 50.89% | +0.06 | 15.15% | 17th | 65.67% | — |
| Wraith King | 54.89% | 54.81% | +0.08 | 12.68% | 27th | 0.00% | — |
| Spectre | 53.26% | 53.28% | −0.02 | 9.68% | 39th | 0.00% | — |
| Rubick | 49.56% | 49.54% | +0.02 | 19.28% | 4th | 25.97% | — |
| Techies | 51.03% | 51.07% | −0.04 | 13.81% | 22nd | 69.42% | — |

Статистика по WR (10 героев):
- Среднее абсолютное расхождение: **~0.05 п.п.**
- Максимальное: **0.09 п.п.** (Sniper)
- Всеhero в пределах ±0.1 п.п.

---

## 7. Сводная таблица сравнения

### Win Rate

| Герой | STRATZ WR | OpenDota WR | Dotabuff WR | Δ STRATZ | Δ OpenDota |
|-------|-----------|-------------|-------------|----------|------------|
| Juggernaut | 52.88% | 52.57% | 52.61% | +0.27 | −0.04 |
| Phantom Lancer | 53.25% | 52.82% | 52.90% | +0.35 | −0.08 |
| Pudge | 51.10% | 51.39% | 51.37% | −0.27 | +0.02 |
| Lion | — | 48.72% | 48.65% | — | +0.07 |
| Sniper | — | 49.93% | 49.84% | — | +0.09 |
| Necrophos | 50.87% | 50.95% | 50.89% | −0.02 | +0.06 |
| Wraith King | 55.08% | 54.89% | 54.81% | +0.27 | +0.08 |
| Spectre | — | 53.26% | 53.28% | — | −0.02 |
| Rubick | — | 49.56% | 49.54% | — | +0.02 |
| Techies | — | 51.03% | 51.07% | — | −0.04 |

### Pick Rate

| Герой | OpenDota Pick | Dotabuff Pick (основной) | Dotabuff Popularity |
|-------|---------------|--------------------------|---------------------|
| Juggernaut | 18.01% | не указан | 5th |
| Phantom Lancer | 11.93% | не указан | 31st |
| Pudge | 27.26% | не указан | 1st |
| Lion | 24.44% | не указан | 2nd |
| Sniper | 19.87% | не указан | 3rd |
| Necrophos | 15.15% | не указан | 17th |
| Wraith King | 12.68% | не указан | 27th |
| Spectre | 9.68% | не указан | 39th |
| Rubick | 19.28% | не указан | 4th |
| Techies | 13.81% | не указан | 22nd |

Примечание: Dotabuff не отображает общий пикрейт героя как единственное число — только внутри фансетов. OpenDota пикрейт — относительная метрика (`1000 × pub_pick / Σpub_pick`, кап 100), а не процент всех матчей.

### Ban Rate

| Герой | OpenDota Ban (pro-уровень) | STRATZ Ban (из `banDay`, если загружено) | Dotabuff Ban |
|-------|---------------------------|------------------------------------------|--------------|
| Juggernaut | 55.56% | — | — |
| Phantom Lancer | 63.64% | — | — |
| Pudge | 13.79% | — | — |
| Lion | 50.00% | — | — |
| Sniper | 60.00% | — | — |
| Necrophos | 65.67% | — | — |
| Wraith King | 0.00% | — | — |
| Spectre | 0.00% | — | — |
| Rubick | 25.97% | — | — |
| Techies | 69.42% | — | — |

Примечание: OpenDota банрейт — это **про-уровень** (`pro_ban/(pro_pick+pro_ban)`), а не публичный банрейт. STRATZ `banDay` даёт семплированный публичный банрейт (нормировка на 10 банов/матч), но живые запросы к STRATZ API не удались (Kong 403, см. §8). Dotabuff банрейт не доступен публично.

---

## 8. Проблемы с живыми запросами к STRATZ API

STRATZ GraphQL (`https://api.stratz.com/graphql`) с токеном из `%APPDATA%\VETMO\secrets.env` возвращает **HTTP 403 (Kong: "A bearer token is required")** при всех перепробованных вариантах заголовков:
- `Authorization: Bearer <token>`
- `Authorization: <token>`
- `X-Stratz-Token: <token>`
- с `curl_cffi impersonate=chrome` и без

Возможные причины: токен отозван/истёк, требуется STRATZ+ подписка, или Kong валидирует JWT-claims, которые не совпадают. Живые данные STRATZ получить не удалось; сравнение STRATZ→Dotabuff взято из ранее выполненного отчёта `docs/qa-winrate-verification.md`.

---

## 9. Выводы: какое API точнее

### Win Rate
| Источник | Среднее |Δ vs Dotabuff (10 героев) | Комментарий |
|----------|---------|--------------------------|-------------|
| **OpenDota API** | ~0.05 п.п. | excellent | Все 10 героев в пределах ±0.09 п.п. |
| **STRATZ API** | 0.267 п.п. (по 126 героям) | good | Медиана 0.215, 95-й перс. 0.721; максимум 1.146 (Meepo) |

**OpenDota точнее по WR** на проверенной выборке (в 5–10 раз меньшее расхождение). STRATZ тоже приемлемо (±0.3 п.п. для большинства героев), но имеет больше выбросов.

### Pick Rate
- **OpenDota**: даёт относительный пикрейт (доля от всех пиков, capped 100). Непрямо сравним с процентом матчей на Dotabuff, но внутренне консистентен.
- **Dotabuff**: не показывает общий пикрейт как единственное число.
- **STRATZ**: `winDay` даёт `pick_rate = matchCount/total_matches × 100`, что ближе к абсолютному пикрейту, но данные отставали на ~10 дней (в октябре 2026).

### Ban Rate
- **OpenDota**: банрейт только на **про-уровне** (`pro_ban/(pro_pick+pro_ban)`). Для публичной меты не подходит (например, Wraith King 0.00% банов в про, но реально банят в пабах).
- **STRATZ**: `banDay` даёт семплированный публичный банрейт с нормировкой на 10 банов/матч. Это единственный источник публичного банрейта, но семпл меньше полного пула.
- **Dotabuff**: банрейт не публикуется.

---

## 10. Рекомендация: основное API для мета-данных в VETMO

### Рекомендуется: **OpenDota API как основной источник**

Обоснование:
1. **Точность WR**: среднее расхождение vs Dotabuff ~0.05 п.п. (в 5–10 раз лучше STRATZ).
2. **Доступность без ключа**: `GET https://api.opendota.com/api/heroStats` не требует аутентификации, нет Cloudflare/Kong блокировок.
3. **Актуальность**: `heroStats` — скользящий срез публичных матчей, данные свежие (в отличие от STRATZ `winDay`, который отставал на ~10 дней).
4. **Уже интегрирован**: `opendota_client.py` уже реализован с валидатором (T-007), кэшем ≥ 24ч, ретраями и rate-limitem.
5. **Карантин невалидных записей**: `ValidatorService` уже отсекает битые герои и мета-строки (is_validated = False).

### STRATZ API — как дополнительный/альтернативный источник

Использовать для:
- **Банрейта (публичного)**: через `banDay` — единственный источник публичного банрейта в VETMO.
- **Матчапов**: `matchUp` — kontrol-piki и синергии, которых нет в OpenDota `heroStats` (OpenDota даёт только `/heroes/{id}/matchups` — другие эндпоинты).
- **Ранговое расщепление**: `stats(week)` с `groupByBracket`/`groupByPosition` — если нужна метка по рангам.

### Что не использовать как основное
- STRATЗ `winDay` как основной источник WR/пикрейта — большее расхождение vs референсы + задержка данных.
- OpenDota про-банрейт для публичной меты — это не публичный банрейт.

---

## 11. Эндпоинты OpenDota для повторения сравнения (если API недоступен)

Если сеть недоступна или требуется ключ,以下 эндпоинты нужно вызвать:

| Эндпоинт | Параметры | Что возвращает | Как использовать |
|----------|-----------|----------------|------------------|
| `GET /api/heroStats` | нет (или `?limit=N`) | Массив героев с `pub_pick`, `pub_win`, `pro_pick`, `pro_win`, `pro_ban`, tier-показатели `1_pick`..`8_pick`, `1_win`..`8_win` | WR = `pub_win/pub_pick×100`; pick = `1000×pub_pick/Σpub_pick`; ban = `pro_ban/(pro_pick+pro_ban)×100` |
| `GET /api/constants/patch` | нет | Список патчей с `id`, `name`, `date` | Определение текущего патча (7.41f) |
| `GET /api/heroes/{id}/matchups` | `id` = hero_id | Матчапы героя с `games_played`, `wins`, `against_hero_id` | Контрпики/синергии |

**Параметры для сопоставимости с референсами:**
- Режим: OpenDota `heroStats` — это публичные матчи (pub), приблизительно All Pick. Нет явного фильтра по режиму — это ограничение.
- Ранги: OpenDota даёт разбивку по tier 1..8 (`1_pick`/`1_win` … `8_pick`/`8_win`), где 1=Herald … 8=Immortal. Для "все ранги" используется `pub_pick`/`pub_win`.
- Патч: `heroStats` — скользящий срез, привязка к патчу косвенная через `latest_patch()` из `/constants/patch`.

**Dotabuff.com для ручной сверки:** `https://www.dotabuff.com/heroes/<hero-slug>` — раздел "This Week", Win Rate и Popularity rank. Пикрейт/банрейт не доступны как отдельные числа (только внутри фансетов).

---

## 12. Артефакты

- `docs/qa-winrate-verification.md` — предыдущая сверка STRATZ→Dotabuff (126 героев, 0.267 п.п. среднее расхождение WR).
- `docs/qa-admin-security.md` — QA админ/безопасность (206 тестов passed, `.env` не в git).
- `tests/unit/test_stratz_aggregate.py` — тесты нормализации банов и режима STRATZ.

---

## 13. Следующие шаги (T-017, T-018, T-021)

1. Написать unit-тесты для валидатора API-данных (T-007) — проверка win_rate 0–100, существование имён героев, reachable URL иконок.
2. Добавить тест `test_sync_heroes_idempotent_upsert` (Review Focus #3).
3. Добавить тест `test_validator_quarantines_invalid_hero_record` (Review Focus #1).
4. Продолжить интеграционные тесты UI (T-018) с pytest-qt.
5. Финальный прогон `pytest` + `ruff` + `mypy` (T-021).
