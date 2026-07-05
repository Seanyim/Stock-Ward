# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Stock-Ward v4 — builds a standalone Windows app.
#   Build:  build.bat   (or)   pyinstaller stockward.spec
# Output:  dist/Stock-Ward/Stock-Ward.exe   (onedir; ship the whole folder)
import os
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None

hiddenimports = (
    collect_submodules("uvicorn")
    + collect_submodules("engine")
    + collect_submodules("engine.providers")
    + collect_submodules("modules")
    + collect_submodules("webview")
    + ["server", "yfinance", "pandas", "numpy", "requests", "dateutil",
       "anyio", "click", "h11", "sniffio", "starlette", "fastapi",
       "webview", "webview.platforms.winforms", "clr_loader", "proxy_tools"]
)

# bundle the web assets + an example keys file (read-only)
datas = [
    ("web", "web"),
    ("data/api_keys.example.json", "data"),
]
# yfinance ships data files it needs at runtime
try:
    datas += collect_data_files("yfinance")
except Exception:
    pass

a = Analysis(
    ["run.py"],
    pathex=[os.path.abspath(".")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["streamlit", "matplotlib", "tkinter", "PyQt5", "PySide2"],
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="Stock-Ward",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,          # keep a console so users see the local URL / errors
    disable_windowed_traceback=False,
    icon=None,
)
coll = COLLECT(
    exe, a.binaries, a.zipfiles, a.datas,
    strip=False, upx=True, upx_exclude=[],
    name="Stock-Ward",
)
