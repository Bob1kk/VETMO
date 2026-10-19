# VETMO — Specification

**Project:** VETMO (Dota 2 All Pick draft assistant)  
**Date:** 2026-10-19  
**Deadline:** 2026-10-21 (Wednesday)  
**Author:** Plan Architect (via `writing-plans` skill)  
**Status:** Draft for review

---

## 1. Vision

VETMO is a Windows desktop assistant for Dota 2 All Pick drafts. It opens to a mini news/meta window, lets the user configure an always-on-top overlay, and shows recommended heroes by position (1–5) on both sides of the screen during the draft phase (2 picks → 2 picks → 1 pick). Data comes from free public sources (OpenDota API) and is cached locally; optional cloud sync via Supabase.

---

## 2. Users & Roles

| Role | Who | What they do |
|---|---|---|
| Player | Dota 2 player (solo or party) | Opens app, reads news/meta, configures overlay, starts overlay during draft, follows hero recommendations |
| Power user | Same player | Tweaks overlay position/opacity/theme, manually corrects pick recognition, checks data freshness |

---

## 3. Functional Requirements

| ID | Requirement | Acceptance / Verification |
|---|---|---|
| FR-001 | **Launcher window**: on start, show a mini window with patch news, current meta, settings entry, theme/wallpaper selector, and a big “Start Overlay” button. | Window appears within 3 s; contains at least one news item and the overlay button. |
| FR-002 | **Overlay settings menu**: position (left/right/both), opacity, always-on-top toggle, click-through toggle, theme/wallpaper choice. | Settings are saved and restored on next launch. |
| FR-003 | **Overlay button**: show/hide the overlay from the launcher. | Clicking toggles overlay visibility without closing launcher. |
| FR-004 | **Overlay content**: recommended heroes for positions 1–5 on Radiant side (left) and Dire side (right), based on meta/counters. | At least one hero card per position is visible when overlay is active. |
| FR-005 | **Draft sequence**: All Pick order — 2 picks, then 2 more picks, then 1 pick (10 picks total). UI shows current step and which team is picking. | Step indicator advances correctly; cannot exceed 10 picks. |
| FR-006 | **Data sync from OpenDota**: pull hero list, win rates, pick rates, hero vs hero counters, and synergies; cache locally. | Local DB contains 120+ heroes and meta snapshots after first sync. |
| FR-007 | **Data validation**: an independent validator checks API data for reality (hero names exist, win rate 0–100, icon URLs reachable, patch version sane). | Invalid records are quarantined, not shown to user. |
| FR-008 | **Manual pick entry**: user can manually select picked heroes per team/position if CV fails. | Draft state updates and recommendations refresh. |
| FR-009 | **CV screen capture (experimental)**: capture Dota 2 pick screen and match hero icons via OpenCV template matching. | Module runs without crashing; detected picks can be confirmed or corrected manually. |
| FR-010 | **Optional Supabase sync**: if `SUPABASE_URL` and `SUPABASE_KEY` are set, push/pull meta snapshots. | App starts and works even if Supabase is unreachable or credentials missing. |
| FR-011 | **Packaging**: single-file Windows `.exe` installer. | Running the installer on clean Windows installs VETMO and creates a Start Menu entry. |

---

## 4. Non-Functional Requirements

| ID | Requirement | Verification |
|---|---|---|
| NFR-001 | Cold start < 3 seconds. | Measured with `time` from double-click to first visible window. |
| NFR-002 | Overlay is borderless, always-on-top, supports transparency/click-through. | Visual check on Windows 10/11; does not steal focus from Dota 2. |
| NFR-003 | OpenDota API rate limit respected; data cached at least 24 h. | No more than 60 requests/minute observed; offline use works with cached data. |
| NFR-004 | UI language: Russian. | All user-facing strings in Russian. |
| NFR-005 | No business logic inside Qt widgets; UI ↔ ViewModel ↔ Service separation. | Code review: no SQL or API calls in `ui/` package. |
| NFR-006 | Secrets never committed; configured via `.env` / `pydantic-settings`. | `.env.example` present, `.env` in `.gitignore`. |

---

## 5. Scope

**In scope (MVP for 2 days):**
- Windows desktop app (PySide6).
- Local SQLite DB with Alembic migrations.
- OpenDota API client with caching and validation.
- Launcher: news/meta, settings, overlay toggle, theme selector.
- Overlay: borderless, always-on-top, hero recommendations by position (1–5) for both teams.
- Draft state machine (2-2-1).
- Manual pick entry.
- Experimental CV icon matching (OpenCV + mss).
- PyInstaller one-file build.

**Out of scope (explicitly deferred):**
- n8n integration (documented as future hook, not implemented).
- Supabase as primary database (optional client only; local SQLite is source of truth).
- Parsing live Dota 2 game memory or network packets (only screen capture).
- Multi-user accounts, auth, cloud user profiles.
- Mobile or macOS/Linux builds.
- Voice commands, in-game sound alerts.

---

## 6. Assumptions

| # | Assumption | Rationale |
|---|---|---|
| A1 | OS is Windows 10/11 (user environment is `win32`). | Overlay implementation targets Win32 always-on-top/transparent windows. |
| A2 | OpenDota API is free and accessible without auth key for public endpoints. | Public REST API used; rate limit ~60 req/min assumed, caching mitigates. |
| A3 | User has Dota 2 running in borderless/windowed mode for CV overlay to work. | Fullscreen exclusive mode blocks screen capture. |
| A4 | Supabase credentials may or may not be provided; app must not fail without them. | Optional integration gate. |
| A5 | n8n is not implemented in this 2-day sprint. | Too much setup time; deferred to v2. |
| A6 | Hero icon images for CV are downloaded once from OpenDota and stored locally. | Avoids repeated network calls during template matching. |

---

## 7. Open Questions

| # | Question | Owner |
|---|---|---|
| Q1 | Will user provide Supabase URL/key, or should we skip cloud sync entirely? | User |
| Q2 | Is Dota 2 client in windowed/borderless mode during draft, or exclusive fullscreen? | User |
| Q3 | Should overlay show enemy team picks (dire) or only friendly recommendations? | User |
