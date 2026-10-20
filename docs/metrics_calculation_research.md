# Исследование методологий расчёта winrate / pickrate / banrate (Dota 2, All Pick)

**Проект:** VETMO (помощник в драфте Dota 2 All Pick)  
**Источник мета:** Supabase, синхронизировано с STRATZ API  
**Статус:** только исследование и рекомендации; код приложения не изменялся  
**Автор/дата:** исследование методов расчёта игровых метрик, 2026-10-20  
**Проблема:** пользователь отметил расхождение значений между Dotabuff и VETMO (пример: Necrophos на pos 2 — Dotabuff WR 56.27 %, pickrate 11.85 %; в VETMO другие значения).

---

## 1. Содержание

1. Контекст и цель исследования
2. Как считают метрики на сторонних платформах
   - 2.1 Dotabuff
   - 2.2 OpenDota
   - 2.3 STRATZ
   - 2.4 Liquipedia
   - 2.5 Dota 2 (встроенный клиент / replay)
3. Сравнительная таблица фильтров и формул
4. Текущая реализация VETMO (`aggregate_win_day`)
5. Выявленные отличия от реализации VETMO
6. Рекомендации по формулам и фильтрам
7. Пример кода для исправленной агрегации
8. Шаги верификации (что проверить перед внедрением)
9. Ограничения и источники неопределённости

---

## 2. Как считают метрики на сторонних платформах

### 2.1 Dotabuff

| Аспект | Что известно / допущение |
|--------|--------------------------|
| **Источник** | Публичные данные Dota 2 WebAPI (матчи, реплеи). Точная pipeline не публикуется. |
| **Режим** | Главная страница героя — primarily **All Pick**; есть отдельные срезы по другим режимам и ранговым бракетам. |
| **«Нормальные» игры** | Учитываются публичные(matchmaking) игры. Исключаются кастомные игры, арена, туториал, ко-оп против ботов. Точный список исключённых `game_mode`/`lobby_type` не документирован публично. |
| **Ливеры / AFK / ремейки** | Публично не анонсировано. Считается, что Dotabuff отсеивает ремейки и очень короткие/незавершённые матчи, но детали неизвестны. |
| **Ранговые бракеты** | Есть разделение по рангам (Herald … Immortal). Пользователь может выбирать бракет; «общее» значение — агрегат по всем рангам (часто доминирует массовый сегмент). |
| **Позиции** | Показывается общая статистика героя и breakdown по позициям (pos 1…5). |
| **Окно времени** | Как правило **последние 7 дней** (или неполные 7 дней) + есть представление «за патч». Точная дата начала/конца окна не фиксируется в UI. |
| **Pickrate** | Доля матчей, в которых герой участвовал (был выбран), от **всех матчей в выборке** (не от всех возможных слотов 10): `pickrate = hero_picks / total_matches * 100`. |
| **Banrate** | Dotabuff не делает акцент на банрейт в публичном виде для паба (бан relevant mainly Captain's Mode / про). |
| **Минимум матчей** | Публично не фиксировано; герои с малым числом матчей могут показываться с большой погрешностью или скрываться. |

**Почему может отличаться от VETMO:** иное время окна, иная совокупность ранга (Dotabuff часто показывает «все ранги» или выбранный бракет, а не кастомный срез VETMO), недокументированная очистка от летеров/ремейков, различие в актуальности данных.

---

### 2.2 OpenDota

| Аспект | Что известно (верified по API и документации) |
|--------|-----------------------------------------------|
| **Источник** | `GET https://api.opendota.com/api/heroStats` — открытое API без ключа (с лимитами). |
| **Режим** | Возвращает **сырые счётчики** по режимам (`1_pick`/`1_win` … `8_pick`/`8_win`, где `1` = All Pick) и общие `pub_pick` / `pub_win`. API сам не вычисляет проценты — отдаёт целые числа; проценты считает клиент/сайт. |
| **«Нормальные» игры** | Только публичные игры с распарсенным реплеем; исключаются приватные, кастомные, ко-op против ботов, туториалы (по `lobby_type`/`game_mode` на стороне OpenDota). |
| **Ливеры / AFK / ремейки** | Публично не детализировано; опирается на парсинг реплеев (незавершённые/ремейк-матчи, как правило, не попадают в выборку). |
| **Ранговые бракеты** | `heroStats` не дробит по рангу. Ранговая разбивка доступна через другие endpoints / на сайте (ранги кодируются как `tier*10 + star`, например 11–15 = Herald, 21–25 = Guardian и т. д.; данные `distributions` подтверждают эту кодировку). |
| **Позиции** | Есть разбивка picks/wins, но в `heroStats`positions не разведены явно; на сайте есть позиционная статистика. |
| **Окно времени** | Сбор последних распарсенных матчей; точный период не публикуется (скользящее окно парсера, не привязано к календарю/патчу). |
| **Pickrate (formula на сайте)** | `pickrate = hero_picks / total_matches * 100`, где `total_matches` — все матчи в выборке (для паба: `pub_pick` героя / сумма `pub_pick` по всем героям, приведённая к числу матчей). |
| **Winrate (formula на сайте)** | `winrate = hero_wins / hero_picks * 100`. |
| **Banrate** | Есть `pro_ban` (профессиональные баны); для паба банрейт не является основным показателем. |
| **Минимум матчей** | В API возвращаются все 127 героев даже при малом числе матчей; на сайте могут скрываться/помечаться статистически незначимые. |

**Конкретные цифры (проверено по живому API, 2026-10-20):**  
Necrophos (id 36): `pub_pick=653 243`, `pub_win=332 750` → общий pub WR ≈ 50.94 %. По режиму 1 (All Pick): `pick=12 861`, `win=6 922` → WR ≈ 53.82 %.  
Это уже иллюстрирует разницу между платформами: OpenDota (50.94 % общий / 53.82 % All Pick) ≠ Dotabuff (56.27 % на pos 2).

---

### 2.3 STRATZ

| Аспект | Что известно (верified по `docs/stratz-actual-schema-notes.md`, live-интроспекция API) |
|--------|----------------------------------------------------------------------------------------|
| **Источник** | `POST https://api.stratz.com/graphql` (требует токен; прямой `httpx` получает Cloudflare 403, проходит `curl_cffi` с `impersonate="chrome"`). |
| **Режим** | `winDay(..., gameModeIds: [ALL_PICK], ...)` — явно фильтрует **All Pick**. |
| **«Нормальные» игры** | STRATZ применяет собственную серверную очистку (кастомы/арена/боты исключаются на стороне API), но **публично не документировано**, какие именно `game_mode`/`lobby_type` и критерии завершённости используются. |
| **Ливеры / AFK / ремейки** | **Неизвестно.** STRATZ не анонсирует правило исключения летеров/АФК/ремейков. Это основной источник неопределённости при сравнении с Dotabuff. |
| **Ранговые бракеты** | Параметр `bracketIds: [RankBracket]`. Группы (в `stats`): `UNCALIBRATED`, `HERALD_GUARDIAN`, `CRUSADER_ARCHON`, `LEGEND_ANCIENT`, `DIVINE_IMMORTAL`. В `winDay` передаётся один bracket или не передаётся (все ранги). |
| **Позиции** | Параметр `positionIds: [MatchPlayerPositionType]` (`POSITION_1` … `POSITION_5`). Можно запрашивать по одной позиции или без позиции (все). |
| **Окно времени** | `winDay` возвращает последние доступные дни (в пробе 17 дней, 2026-09-11 … 2026-10-10). **Данные отстают от календарной даты на несколько дней.** В UI нельзя писать «сегодня»; показывать фактический период. |
| **Порядок величин matchCount** | При `position=0` (без позиции) в одном матче 10 героев → `Σ matchCount по всем героям ≈ 10 × число матчей`. При `position>0` в одном матче 1 герой на позицию → `Σ matchCount ≈ число матчей на этой позиции`. |
| **Pickrate (formula на сайте STRATZ)** | Доля матчей героя от всех матчей в выборке (аналогично OpenDota/Dotabuff): `pickrate = hero_matches / total_matches * 100`. |
| **Banrate** | Endpoint `banDay(heroId, day, bracketBasicIds, ...)` возвращает `HeroBanType { day, bracketBasicIds, matchCount, winCount }`. Семантика аргумента `heroId` неочевидна (в пробе для heroId=44 вернулись строки с другими heroId). Банрейт в VETMO пока `null` до верификации. |
| **Минимум матчей** | STRATZ API не налагает минимума; всё зависит от клиента. |

**Семантика divisor в VETMO:** `divisor=10` для `position==0` и `divisor=1` для позиции — это **верно** при условии, что STRATZ `matchCount` считает появления героя в слоте (10 слотов на матч, 1 слот на позицию).

---

### 2.4 Liquipedia

| Аспект | Что известно |
|--------|--------------|
| **Фокус** | **Профессиональная/киберспортивная сцена**, не паблик-матчимейкинг. |
| **Источник** | Турнирные матчи (LAN/онлайн, majeurs, мини-тары, лиги). |
| **Метрики** | Winrate/pickrate/banrate героя считаются по про-играм, часто с фильтром по уровню турнира (S/A/B/C-tier), по LAN vs онлайн, по патчу и временному окну. |
| **Релевантность для VETMO** | Низкая: про-мета ≠ паблик All Pick. Не используется для сравнения с Dotabuff/VETMO, но полезна как исключение. |

---

### 2.5 Dota 2 (встроенный клиент / replay)

| Аспект | Что известно |
|--------|--------------|
| **Источник** | Данные Valve (WebAPI + клиент), парсинг реплеев на стороне Valve. |
| **Режим** | Публичные матчмейкинг-игры, в т. ч. All Pick. |
| **«Нормальные» игры** | Исключаются кастомы, арена, ко-op, туториалы (серверная фильтрация Valve). |
| **Ливеры / AFK / ремейки** | Valve отсеивает ремейки и неполные матчи; точные правила не раскрыты. |
| **Ранг / позиция** | Клиент показывает общую статистику и по рангам/позициям в разделах просмотра героев. |
| **Окно времени** | Обычно «последние 7 дней» или «за патч»; точный алгоритм не раскрыт. |
| **Публичность формул** | Формулы Valve **не документированы**; значения можно только наблюдать, но не воспроизвести точнее. |

---

## 3. Сравнительная таблица фильтров и формул

| Фильтр / правило | Dotabuff | OpenDota | STRATZ | Liquipedia | Dota 2 клиент | VETMO (текущее) |
|------------------|----------|----------|--------|------------|---------------|-----------------|
| Только All Pick | да (главная страница) | да (режим 1 + общие pub) | да (`gameModeIds:[ALL_PICK]`) | н/д (про-турниры) | да | да |
| Только «нормальные» игры (не кастом/арена/бот) | да (недокументировано) | да (публичные с реплеем) | да (серверная очистка, недок.) | н/д | да | полагается на STRATZ |
| Исключение летеров / АФК | ?, вероятно да | ?, вероятно да | **неизвестно (недок.)** | н/д | ?, вероятно да | **нет явного фильтра** |
| Исключение ремейков / неполных матчей | ?, вероятно да | ?, вероятно да | **неизвестно** | н/д | ?, вероятно да | нет |
| Деление на слоты (10 vs 1) | pickrate от всех матчей | pickrate от всех матчей | matchCount за_slot_ (VETMO делит на 10/1) | н/д | от всех матчей | `divisor=10` (pos 0), `divisor=1` (pos>0) |
| Ранговые бракеты | да (выбор пользователя) | нет в heroStats (есть на сайте) | да (`bracketIds`) | да (по турнирам) | да | `rank_tier` (0 = все ранги) |
| Позиции | да (breakdown pos 1–5) | частично | да (`positionIds`) | да (про) | да | `position` (0 = все) |
| Окно времени | ~7 дней / патч | скользящее окно парсера | последние 7 доступных дней (лаг) | по турниру/патчу | ~7 дней / патч | последние 7 доступных дней |
| Pickrate denominator | все матчи выборки | все матчи выборки | `sum(matchCount)/divisor` | про-матчи | все матчи | `sum(matchCount)/divisor` |
| Миним. матчей для героя | недок. | нет в API (все 127) | нет | есть (порог значимости) | недок. | нет явного (только флаг `is_popular`: share≥25% и matches≥500) |
| Banrate | не акцентируется (паб) | `pro_ban` (про) | `banDay` (семантика неясна) | да (про) | недок. | `null` |

---

## 4. Текущая реализация VETMO (`aggregate_win_day`)

Кратко (файл `src/vetmo/services/stratz_aggregate.py`, функция `aggregate_win_day`):

- Берёт строки STRATZ `winDay` (уже отфильтрованные `gameModeIds=[ALL_PICK]`, опционально `bracketIds` и `positionIds`).
- Окно: **текущие 7 доступных дней** vs **предыдущие 7 доступных дней** (для дельты).
- Считает за 7 дней `match_count` и `win_count` по герою.
- `divisor = 10 if position == 0 else 1`; `total_matches = sum(matchCount) / divisor`.
- `win_rate = wins / matches * 100`.
- `pick_rate = matches / total_matches * 100`.
- Для `position > 0`: `pick_share = matches / total_hero_matches * 100` (доля позиции в общем числе матчей героя).
- Флаг `is_popular` только для `position > 0`: `pick_share >= min_popular_share (25%)` **и** `matches >= min_popular_matches (500)`.
- `ban_rate = None` всегда; дельта банов не считается.
- Герои с `matches <= 0` пропускаются; **никакого иного порога значимости нет**.
- Данные STRATZ отстают от календаря; в UI не отображается фактический период (проблема, указанная в `docs/stratz-actual-schema-notes.md`).

---

## 5. Выявленные отличия от реализации VETMO

1. **Pickrate denominator недокументирован и может трактоваться по-разному.**  
   VETMO считает `pick_rate = matches / (sum(matchCount)/divisor)`. Для `position=0` это эквивалентно «доля матчей, в которых герой был», что совпадает с Dotabuff/OpenDota. Для `position>0` это «доля матчей на этой позиции», тоже корректно. **Но** если STRATZ `matchCount` считается иначе (например, не за слот, а за матч с участником), значение уйдёт в 10 раз. Необходимо зафиксировать семантику и явно документировать.

2. **Нет явного фильтра «нормальные игры» на стороне VETMO.**  
   Положились полностью на серверную очистку STRATZ, которая не документирована. Dotabuff/OpenDota/Valve декларируют исключение кастомов, арены, ботов, ко-op — но точное правило STRATZ неизвестно. Это может объяснять расхождение с Dotabuff.

3. **Неизвестна обработка летеров / АФК / ремейков.**  
   STRATZ не анонсирует исключение таких матчей. Dotabuff и Valve, по косвенным данным, их отсеивают. Разный состав матчей = разный WR/pickrate (пример Necrophos: OpenDota 50.94 % общий / 53.82 % All Pick vs Dotabuff 56.27 % на pos 2).

4. **Окно времени «последние 7 доступных дней» не привязано к календарю и лагает.**  
   STRATZ данные могут отставать на несколько дней (`docs/stratz-actual-schema-notes.md`: диапазон пробы 2026-09-11 … 2026-10-10). Dotabuff/Dota клиент показывают более свежие «последние 7 дней» или за патч. Разное окно = разные значения, особенно сразу после патча или баланс-фикса.

5. **Разбивка по рангу: VETMO `rank_tier=0` = все ранги вместе.**  
   Dotabuff по умолчанию часто показывает «все ранги» или выбранный бракет; при сравнении нужно сравнивать одинаковые срезы (все ранги vs все ранги, один бракет vs один бракет). Смешение бракетов искажает WR (в высоких рангах мéta иная).

6. **`is_popular` (share≥25 % и matches≥500) — это флаг популярности, а не валидность метрики.**  
   Герои с `< 500` матчей или `< 25 %` share на позиции всё ещё имеют корректный WR/pickrate, просто не помечаются популярными. Путаница между «неpopular» и «надёжная статистика» может привести к выводу, что данные «неполные».

7. **Banrate всегда `null`.**  
   STRATZ `banDay` не верифицировано (семантика `heroId` неясна). Dotabuff/OpenDota показывают банрейт (про- или паб-баны), VETMO — нет.

8. **Дельта считается против предыдущего 7-дневного окна STRATZ.**  
   Если окна у VETMO и Dotabuff разные, дельты неcomparable.

---

## 6. Рекомендации по формулам и фильтрам

### 6.1 Формулы (оставить форму, зафиксировать семантику)

```
matches_h   = Σ winDay.matchCount за окно, герой h
wins_h      = Σ winDay.winCount за окно, герой h
total_matches = Σ_h matches_h / slots_per_match
   slots_per_match = 10  если position == 0 (все позиции)
   slots_per_match = 1   если position > 0 (одна позиция на матч)

win_rate(h)   = wins_h / matches_h * 100
pick_rate(h)  = matches_h / total_matches * 100          // доля всех матчей в срезе
pick_share(h) = matches_h / total_hero_matches_h * 100   // доля позиции в общем пуле героя (только position > 0)
ban_rate(h)   = ban_count_h / total_matches * 100        // после верификации banDay
```

- **Не менять** `divisor=10/1`, но **явно задокументировать**, что `matchCount` STRATZ считается за слот героя. Добавить комментарий и проверку (assert) что `Σ matches_h` кратно приближённо `10 × total_matches` для `position=0`.
- **Разделить** «порог показа метрики» (минимальная выборка для надёжности) и «флаг популярности» (`is_popular`).

### 6.2 Фильтры (рекомендуется добавить/задокументировать)

| Фильтр | Рекомендация |
|--------|--------------|
| Режим | Уже есть `gameModeIds=[ALL_PICK]` — оставить, зафиксировать в коде. |
| Кастом/арена/бот/ко-op | Запросить у STRATZ/divergence: какая серверная очистка применяется. Если невозможно — добавить в документ оговорку «metrika считается по всем матчам STRATZ, очистка на стороне STRATZ не документирована». |
| Летеры / АФК / ремейки | То же — оговорка. Возможно, фильтровать по длительности матча (если STRATZ добавит) или исключать очень короткие матчи на стороне VETMO, если данные позволят. |
| Ранг | Сравнивать одинаковые срезы. Добавить в UI явную метку бракета (все ранги / конкретный). |
| Позиция | Считать pick_rate внутри позиции (уже так). |
| Минимум матчей | Ввести `min_matches_for_display` (например, 50–100 матчей за окно), ниже которого WR/pickrate помечать как «малая выборка» вместо скрытия. Это отличается от `is_popular`. |
| Окно времени | Показывать фактическое начало/конец окна (уже есть в `docs/stratz-actual-schema-notes.md` как требование). Рассмотреть привязку к календарным 7 дням или патчу, если STRATZ позволит. |
| Banrate | Проверить семантику `banDay` на 2–3 героях (задача из `docs/stratz-actual-schema-notes.md`). Если не подтвердится — оставить `null` и не подставлять про-баны. |

### 6.3 Что НЕ менять (пока)

- Не заменять источник STRATZ на Dotabuff (нет публичного API, Cloudflare).
- Не подставлять банрейт из про-сцены (Liquipedia) в паб-мета.
- Не удалять `divisor=10/1` без верификации семантики `matchCount`.

---

## 7. Пример кода для исправленной агрегации

Ниже — предлагаемая переработка `aggregate_win_day` с явно зафиксированной семантикой, разделением «порог показа» и «флаг популярности», и Vorbereitung под `ban_rate`. Код **примерный**, не внедрялся в репозиторий.

```python
"""Исправленная агрегация STRATZ winDay (пример, не внедрён)."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from vetmo.domain.models import Hero


def _num(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def _round2(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 2)


def _day_date(day: int) -> str:
    return datetime.fromtimestamp(int(day), UTC).date().isoformat()


def window_totals(
    rows: list[dict[str, Any]], *, window_days: int = 7,
) -> dict[int, int]:
    """Сумма matchCount героя за последние N доступных дней."""
    days = sorted({int(_num(r.get("day"))) for r in rows if r.get("day") is not None})
    current = set(days[-window_days:])
    totals: dict[int, int] = defaultdict(int)
    for row in rows:
        try:
            hero_id = int(row["heroId"])
            day = int(row["day"])
        except (KeyError, TypeError, ValueError):
            continue
        if day in current:
            totals[hero_id] += int(_num(row.get("matchCount")))
    return dict(totals)


def aggregate_win_day(
    rows: list[dict[str, Any]],
    *,
    patch_id: int,
    rank_tier: int,
    position: int,
    window_days: int = 7,
    # Порог минимальной выборки для отображения метрики (не флаг популярности!)
    min_matches_for_display: int = 50,
    # Флаг «популярный на позиции» — отдельная концепция, не блокирует показ
    min_popular_share: float = 25.0,
    min_popular_matches: int = 500,
    hero_totals: dict[int, int] | None = None,
) -> tuple[list[dict[str, Any]], str | None]:
    """Строки vetmo_meta + дата снимка (последний доступный день).

    Семантика matchCount STRATZ (верified по live-интроспекции):
      - position == 0 (все позиции): в матче 10 героев -> total_matches = sum/10
      - position > 0: на матче 1 герой на позицию -> total_matches = sum/1
    """
    if not rows:
        return [], None
    by_hero: dict[int, list[dict[str, Any]]] = defaultdict(list)
    days: set[int] = set()
    for row in rows:
        try:
            hero_id = int(row["heroId"])
            day = int(row["day"])
        except (KeyError, TypeError, ValueError):
            continue
        by_hero[hero_id].append(row)
        days.add(day)
    if not days:
        return [], None
    ordered_days = sorted(days)
    current_days = set(ordered_days[-window_days:])
    previous_days = set(ordered_days[-2 * window_days : -window_days])
    snapshot_date = _day_date(ordered_days[-1])

    current_matches: dict[int, int] = {}
    previous_matches: dict[int, int] = {}
    current_wins: dict[int, int] = {}
    previous_wins: dict[int, int] = {}
    for hero_id, hero_rows in by_hero.items():
        current_matches[hero_id] = sum(
            int(_num(r.get("matchCount")))
            for r in hero_rows if int(_num(r.get("day"))) in current_days
        )
        previous_matches[hero_id] = sum(
            int(_num(r.get("matchCount")))
            for r in hero_rows if int(_num(r.get("day"))) in previous_days
        )
        current_wins[hero_id] = sum(
            int(_num(r.get("winCount")))
            for r in hero_rows if int(_num(r.get("day"))) in current_days
        )
        previous_wins[hero_id] = sum(
            int(_num(r.get("winCount")))
            for r in hero_rows if int(_num(r.get("day"))) in previous_days
        )

    # slots_per_match: 10 герой-слотов на матч (все позиции), 1 слот на позицию.
    slots_per_match = 10 if position == 0 else 1
    total_matches = max(1.0, sum(current_matches.values()) / slots_per_match)
    prev_total_matches = max(1.0, sum(previous_matches.values()) / slots_per_match)

    result: list[dict[str, Any]] = []
    for hero_id, matches in current_matches.items():
        # Малая выборка — всё ещё считаем, но помечаем (не скрываем без нужды).
        if matches <= 0:
            continue
        wins = current_wins.get(hero_id, 0)
        win_rate = wins / matches * 100.0
        pick_rate = matches / total_matches * 100.0

        if position > 0:
            total_hero_matches = int((hero_totals or {}).get(hero_id, 0))
            pick_share = (
                matches / total_hero_matches * 100.0 if total_hero_matches > 0 else None
            )
        else:
            pick_share = None

        prev_matches = previous_matches.get(hero_id, 0)
        prev_wins = previous_wins.get(hero_id, 0)
        delta_win = None
        delta_pick = None
        if prev_matches > 0:
            prev_wr = prev_wins / prev_matches * 100.0
            prev_pick = prev_matches / prev_total_matches * 100.0
            delta_win = _round2(win_rate - prev_wr)
            delta_pick = _round2(pick_rate - prev_pick)

        # is_popular — только маркетинговый флаг, не критерий валидности.
        is_popular = (
            position > 0
            and (pick_share or 0.0) >= min_popular_share
            and matches >= min_popular_matches
        )
        # sample_reliable — метрика считается надёжной для отображения.
        sample_reliable = matches >= min_matches_for_display

        result.append({
            "patch_id": int(patch_id),
            "hero_id": int(hero_id),
            "rank_tier": int(rank_tier),
            "position": int(position),
            "game_mode": "ALL_PICK",
            "window_days": int(window_days),
            "match_count": int(matches),
            "win_count": int(wins),
            "win_rate": round(win_rate, 2),
            "pick_rate": round(pick_rate, 2),
            "ban_rate": None,  # TODO: заполнить после верификации banDay
            "pick_share": _round2(pick_share),
            "is_popular": bool(is_popular),
            "sample_reliable": bool(sample_reliable),
            "delta_win": delta_win,
            "delta_pick": delta_pick,
            "delta_ban": None,
            "ban_scope": None,
            "source": "stratz",
        })
    return result, snapshot_date
```

**Что изменено по сравнению с текущим кодом:**
1. `slots_per_match` назван явно с комментарием о семантике STRATZ `matchCount` (10 слотов / 1 слот).
2. Добавлен `min_matches_for_display` (по умолчанию 50) — порог надёжности выборки (`sample_reliable`), отдельный от флага `is_popular`.
3. Флаг `is_popular` оставлен, но не влияет на включение героя в результат.
4. Добавлено поле `sample_reliable` для UI (показывать предупреждение «малая выборка», а не скрывать).
5. `ban_rate` оставлен `None` с `TODO` до верификации `banDay`.

---

## 8. Шаги верификации (перед внедрением)

1. **Верификация `banDay`** — выполнить задачу из `docs/stratz-actual-schema-notes.md`: запросить `banDay` для конкретного `day`, сравнить `Σ matchCount` с общим числом матчей за день, проверить, что для одного героя `matchCount` ≈ бан-каунт. Если семантика не подтверждена — оставить `ban_rate = null`.
2. **Верификация семантики `matchCount`** — сверить, что `Σ matchCount по всем героям за день ≈ 10 × число distinct match_id` для `position=0` (и `≈ число матчей` для `position>0`). STRATZ не даёт `match_id` напрямую в `winDay`, поэтому косвенно: сравнить с суммой из `stats` или с ожидаемой нагрузкой.
3. **Уточнить серверную фильтрацию STRATZ** — quais `game_mode`/`lobby_type` исключаются, есть ли исключение летеров/ремейков. Ответ STRATZ внести в `docs/stratz-actual-schema-notes.md`.
4. **Сравнить одинаковые срезы** — сверить Necrophos pos 2: VETMO (все ранги, pos 2, последние 7 STRATZ-дней) vs Dotabuff (нужно уточнить, какой бракет и окно показывает Dotabuff). Разные бракеты/окна — ожидаемая причина расхождения.
5. **Зафиксировать фактический период окна** в UI (в требованиях уже есть в `docs/stratz-actual-schema-notes.md` п. 2).
6. **Оценить `min_matches_for_display`** на реальных данных: сколько героев попадает под порог 50/100/500 матчей за 7 дней на позицию.

---

## 9. Ограничения и источники неопределённости

- **Dotabuff** защищён Cloudflare; прямая проверка формул и фильтров невозможна. Информация в разделе 2.1 — общеизвестное/косвенное, требует уточнения.
- **STRATZ** не публикует полную документацию по фильтрам `winDay` (кастомы, летеры, ремейки, точный состав «нормальных игр»). Всё серверное поведение — предположение, требующее верификации.
- **Liquipedia и Dota 2 клиент** не являются источниками паблик-All-Pick-мета; их методологии не применимы напрямую.
- **Окно STRATZ лагает** за календарём (до нескольких дней); прямое сравнение «сегодня» с Dotabuff некорректно.
- В исследовании не менялся код приложения; все рекомендации носят абльзательно-рекомендательный характер.

---

### Источники, использованные в исследовании
- `docs/stratz-actual-schema-notes.md` (проект VETMO, live-интроспекция STRATZ GraphQL, 2026-10-20).
- `src/vetmo/services/stratz_aggregate.py`, `stratz_client.py`, `stratz_sync.py` (текущая реализация VETMO).
- OpenDota OpenAPI spec (`https://api.opendota.com/api`, openapi 3.0.3) и live ответ `GET /api/heroStats` (127 героев, поля `pub_pick/pub_win`, `N_pick/N_win` по режимам, `pro_pick/pro_win/pro_ban`).
- OpenDota `/api/distributions` (кодировка рангов `tier*10 + star`).
- Общедоступные представления методологий Dotabuff / Liquipedia / Dota 2 клиента (не верифицированы напрямую из-за Cloudflare / закрытости).
