# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build spec for the PC resource logger.

Build with:   pyinstaller Mem_use_log.spec --noconfirm

Produces a ONEDIR build in dist/Mem_use_log/ (run Mem_use_log.exe).
Onedir is deliberate: this app is meant to start with Windows and run all
day, and a onefile build re-extracts the whole bundle into a temp folder on
every launch — slower to start and pointless disk churn for a background
logger. See the note at the bottom if a single file is required anyway.

The app writes config.json, data/ and logs/ next to the executable
(see _resolve_project_root in app/config/settings.py).
"""

from PyInstaller.utils.hooks import collect_data_files

# customtkinter loads its themes and bundled fonts from disk at runtime.
datas = collect_data_files("customtkinter")

hiddenimports = [
    # wmi talks to COM through late-bound win32com, which the static
    # analyser can't see. Without these the GPU/temperature sensors would
    # silently fall back to "unavailable" in the packaged build.
    "win32com",
    "win32com.client",
    "win32com.client.dynamic",
    "pythoncom",
    "pywintypes",
    "wmi",
]

# Large libraries that get pulled in transitively but are never used here.
# PIL stays: customtkinter imports it for CTkImage.
excludes = [
    "numpy", "matplotlib", "pandas", "scipy",
    "IPython", "notebook", "jupyter",
    "pytest", "doctest", "pydoc", "unittest",
    "setuptools", "pip", "wheel",
    "tkinter.test", "test",
    "pystray",          # listed historically, not used by the app
    "PyQt5", "PySide2", "PySide6",
]

a = Analysis(
    ["run.py"],
    pathex=["app"],     # run.py imports scheduler/ui/... as top-level packages
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=1,         # strip asserts and __debug__ blocks
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Mem_use_log",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # UPX shrinks the exe but is a common AV false-positive trigger
    console=False,      # no console window; this is a tray-style background app
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Mem_use_log",
)

# To build a single .exe instead, replace the EXE/COLLECT pair above with a
# single EXE(pyz, a.scripts, a.binaries, a.datas, ..., exclude_binaries=False)
# call. Startup then costs an extraction step on every launch.
