# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for HumanSeeker.

Builds a single-file Windows .exe with:
  - The Flask backend + frontend assets bundled
  - The .env.example bundled
  - The app icon embedded in the .exe and shown on the taskbar
"""

from PyInstaller.utils.hooks import collect_submodules

datas = [
    ("frontend", "frontend"),
    (".env.example", "."),
]

hiddenimports = (
    collect_submodules("backend")
    + collect_submodules("webview")
    + ["flask", "jinja2", "werkzeug", "dotenv"]
)

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="HumanSeeker",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,            # no terminal window — it's a real app
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="frontend/static/icon.ico",
)
