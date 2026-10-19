# -*- mode: python ; coding: utf-8 -*-
"""Спека PyInstaller для VETMO (T-020).

One-file GUI-сборка точки входа src/vetmo/main.py без консоли.
Билд: .\\.venv\\Scripts\\python.exe -m PyInstaller vetmo.spec
Результат: dist/VETMO.exe (запуск на чистом Windows без Python).
"""

import os

ROOT = os.path.abspath(os.path.dirname(SPEC))

# Тяжёлые библиотеки, не входящие в зависимости проекта, не тащим.
_EXCLUDES = [
    "matplotlib",
    "tkinter",
    "PyQt5",
    "PyQt6",
    "tornado",
    "jupyter",
    "IPython",
    "notebook",
    "pytest",
    "pytest_qt",
    "pytest_cov",
    "pytest_mock",
    "numpy.f2py",
    "numpy.tests",
    "numpy.distutils",
]


a = Analysis(
    ["src/vetmo/main.py"],
    pathex=[ROOT, os.path.join(ROOT, "src")],
    binaries=[],
    # Миграции Alembic — data-файлы: в one-file бандле они распаковываются в
    # _MEIPASS с сохранением структуры пакета (vetmo/data/migrations).
    datas=[
        (
            os.path.join(ROOT, "src", "vetmo", "data", "migrations"),
            os.path.join("vetmo", "data", "migrations"),
        ),
    ],
    hiddenimports=["logging.config", "logging.handlers"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=_EXCLUDES,
    noarchive=False,
    optimize=-1,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="VETMO",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
