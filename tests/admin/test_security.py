"""Статические проверки безопасности пользовательской сборки (T-112/T-113).

Пользовательское приложение (``vetmo.main`` + ``vetmo/ui``) не должно
импортировать Admin-код и sync-writer, а также не должно знать имена
секретных переменных. Модуль ``vetmo.infra.supabase_gateway`` общий: в
user-приложении он создаётся только с anon-ключом (см. отдельный тест).
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
USER_ENTRY = ROOT / "src" / "vetmo" / "main.py"
USER_UI_DIR = ROOT / "src" / "vetmo" / "ui"
GATEWAY = ROOT / "src" / "vetmo" / "infra" / "supabase_gateway.py"
SPEC = ROOT / "vetmo.spec"

FORBIDDEN_IMPORTS = (
    "vetmo.admin",
    "vetmo.services.stratz_sync",
    "vetmo.services.stratz_client",
    "vetmo.infra.sync_settings",
)

SECRET_NAMES = (
    "VETMO_SYNC_SERVICE_KEY",
    "VETMO_SYNC_STRATZ_TOKEN",
)


def _user_sources() -> list[Path]:
    sources = [USER_ENTRY, *sorted(USER_UI_DIR.rglob("*.py"))]
    return [path for path in sources if path.is_file()]


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def _is_forbidden(module: str) -> bool:
    return any(
        module == prefix or module.startswith(f"{prefix}.") for prefix in FORBIDDEN_IMPORTS
    )


def test_user_app_does_not_import_admin_or_sync_modules() -> None:
    violations: list[str] = []
    for path in _user_sources():
        for module in sorted(_imported_modules(path)):
            if _is_forbidden(module):
                violations.append(f"{path.relative_to(ROOT)}: {module}")

    assert violations == []


def test_user_app_does_not_reference_sync_secret_variables() -> None:
    violations: list[str] = []
    for path in _user_sources():
        text = path.read_text(encoding="utf-8")
        for name in SECRET_NAMES:
            if name in text:
                violations.append(f"{path.relative_to(ROOT)}: {name}")

    assert violations == []


def test_shared_supabase_gateway_has_no_service_role_credentials() -> None:
    text = GATEWAY.read_text(encoding="utf-8")
    for name in SECRET_NAMES:
        assert name not in text
    assert "sync_settings" not in text


def test_user_app_context_passes_only_anon_settings_to_gateway() -> None:
    text = (USER_UI_DIR / "app_context.py").read_text(encoding="utf-8")

    assert "SupabaseGateway(settings)" in text
    assert "service_key" not in text
    assert "sync_settings" not in text


def test_pyinstaller_spec_does_not_hide_import_admin_modules() -> None:
    text = SPEC.read_text(encoding="utf-8")

    assert "vetmo.admin" not in text
    assert "stratz_sync" not in text
    assert "stratz_client" not in text
