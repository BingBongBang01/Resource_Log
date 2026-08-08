# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build spec for the PC resource logger.

Build with:   pyinstaller Mem_use_log.spec --noconfirm

Produces a ONEFILE build: a single dist/Mem_use_log.exe that runs from
anywhere, with no folder to keep alongside it. Copying just the .exe out of
an old onedir build is what produced "Failed to load Python DLL" — that
build kept the interpreter in the _internal folder next to it.

The trade-off is startup: the bundle is unpacked into a temp folder on
every launch. For an app that starts with Windows and then runs all day
that cost is paid once, which is why onefile wins here.

The app writes config.json, data/ and logs/ next to the executable — never
into the temp folder, which is wiped on exit. See app/utils/paths.py.
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
    # The hidden window that catches WM_QUERYENDSESSION so the logs get
    # flushed when Windows shuts down (app/utils/shutdown.py). Listed
    # explicitly because losing it would silently disable save-on-shutdown
    # in the packaged build only.
    "win32api",
    "win32con",
    "win32gui",
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
    a.binaries,
    a.datas,
    [],
    exclude_binaries=False,     # onefile: everything lands inside the .exe
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

# No COLLECT step: onefile puts everything in the EXE above, so the build
# output is the single file dist/Mem_use_log.exe.
