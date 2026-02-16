# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Batch URL Screenshot
# Run: pyinstaller build_exe.spec

from pathlib import Path

block_cipher = None

# Add templates and static
added_files = [
    ("templates", "templates"),
    ("static", "static"),
]

# Playwright driver (required for browser launch)
try:
    import playwright
    _pw_dir = Path(playwright.__file__).parent
    added_files.append((str(_pw_dir / "driver"), "playwright/driver"))
except Exception:
    pass

a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=[],
    datas=added_files,
    hiddenimports=[
        "flask",
        "playwright",
        "playwright.sync_api",
        "werkzeug",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="screencap_url",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # Show console with URL (open http://127.0.0.1:5000)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
