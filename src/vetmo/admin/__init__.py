"""VETMO Admin — локальная программа обновления reference-данных.

Модули пакета:

- ``context`` — общие зависимости (секреты, STRATZ, Supabase service_role);
- ``repository`` — чтение ``vetmo_*`` для UI;
- ``workers`` — ``SyncRunner(QThread)`` поверх ``sync_all``.

UI-часть (``main``, ``window``, ``tabs``) добавляется отдельной задачей.
"""

__all__: list[str] = []
