# Инструкция по запуску VETMO (для разработчика)

## 1. Уже сделано для тебя

- Python 3.13.9 установлен (найден `py`-лаунчер) ✅
- `uv 0.13.1` установлен через pip (доступен как `uv` в новых окнах терминала; в старых — `py -m uv`) ✅
- Виртуальное окружение создано: `C:\Users\pavel\OneDrive\Документы\Default Project\.venv` ✅
- Все зависимости поставлены (PySide6 6.12, SQLAlchemy 2.1, Alembic, httpx, OpenCV, mss и т.д.) ✅

## 2. Настройка PyCharm (2024.2.3)

1. **File → Open** → выбери папку `C:\Users\pavel\OneDrive\Документы\Default Project` и открой как проект.
2. Настройка интерпретатора: **File → Settings → Project: Default Project → Python Interpreter → Add Interpreter → Add Local Interpreter… → Existing**:
   - Type: Virtualenv Environment
   - Interpreter: `<проект>\.venv\Scripts\python.exe`
3. Проверка: в терминале PyCharm (PowerShell):
   ```powershell
   .\.venv\Scripts\python.exe -m pytest tests/unit -q
   ```
   Должно быть зелёное.
4. Run Configuration: **Run → Edit Configurations… → + → Python**:
   - Script path: `C:\Users\pavel\OneDrive\Документы\Default Project\src\vetmo\main.py`
   - Working directory: `C:\Users\pavel\OneDrive\Документы\Default Project` (важно! иначе не найдёт .env/БД)
5. Если PyCharm ругается на `vetmo` — пометки Mark Directory as **Sources Root** на папке `src`.

## 3. Запуск из терминала (любой)

```powershell
cd "C:\Users\pavel\OneDrive\Документы\Default Project"
.\.venv\Scripts\python.exe src\vetmo\main.py     # GUI
.\.venv\Scripts\python.exe -m pytest tests -q    # все тесты
.\.venv\Scripts\alembic upgrade head             # миграции БД (если чистая vetmo.db)
```

## 4. VS Code (не обязательно)

Открыть папку проекта, выбрать интерпретатор `.venv\Scripts\python.exe`, рекомендация расширения Python + Pylance.

## 5. Полезная информация

- База: `vetmo.db` в корне проекта (создаётся автоматически при первом запуске).
- Секреты: опциональный `.env` (см. `.env.example`); Supabase — если пусто, приложение работает офлайн.
- Логи: `logs/vetmo.log`.
