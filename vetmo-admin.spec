import os

ROOT = os.path.abspath(os.path.dirname(SPEC))


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
    ["src/vetmo/admin/main.py"],
    pathex=[ROOT, os.path.join(ROOT, "src")],
    binaries=[],
    datas=[
        (
            os.path.join(ROOT, "src", "vetmo", "data", "heroes_seed.json"),
            os.path.join("vetmo", "data"),
        ),
        (os.path.join(ROOT, "vetmo_icon.ico"), "."),
        (os.path.join(ROOT, "vetmo_icon.bmp"), "."),
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
    name="VETMO-Admin",
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
