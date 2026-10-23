"""VETMO Admin — локальная программа обновления reference-данных.

Модули пакета:

- ``context`` — общие зависимости (секреты, STRATZ, Supabase service_role);
- ``repository`` — чтение ``vetmo_*`` для UI;
- ``workers`` — ``SyncRunner(QThread)`` поверх ``sync_all``;
- ``window`` / ``tabs`` — PySide6-интерфейс Admin-программы;
- ``main`` — точка входа ``python -m vetmo.admin.main``.
"""

__all__: list[str] = []
