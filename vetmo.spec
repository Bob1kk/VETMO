# -*- mode: python ; coding: utf-8 -*-
"""Спека PyInstaller для VETMO (T-020).

One-file GUI-сборка точки входа src/vetmo/main.py без консоли.
Билд: .\\.venv\\Scripts\\python.exe -m PyInstaller vetmo.spec
Результат: dist/VETMO.exe (запуск на чистом Windows без Python).
"""

import os

ROOT = os.path.abspath(os.path.dirname(SPEC))
_ICONS_DIR = os.path.join(ROOT, "assets", "cache", "icons")
# assets/ наполняется в рантайме и отсутствует в свежем клоне — сборка
# не должна падать на os.listdir несуществующей папки.
_ICON_FILES = (
    sorted(n for n in os.listdir(_ICONS_DIR) if n.endswith(".png"))
    if os.path.isdir(_ICONS_DIR) else []
)

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
        (
            os.path.join(ROOT, "src", "vetmo", "data", "heroes_seed.json"),
            os.path.join("vetmo", "data"),
        ),
        # Иконки приложения (ICO для exe/окна, BMP — исходник) в бандле.
        (os.path.join(ROOT, "vetmo_icon.ico"), "."),
        (os.path.join(ROOT, "vetmo_icon.bmp"), "."),
        # Кэш иконок всех героев (если он собран) — офлайн-иконки в exe.
        *(
            (os.path.join(_ICONS_DIR, name),
             os.path.join("assets", "cache", "icons"))
            for name in _ICON_FILES
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
    icon=os.path.join(ROOT, "vetmo_icon.ico"),
)
