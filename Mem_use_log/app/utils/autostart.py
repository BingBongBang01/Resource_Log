"""Windows "start on boot" support via the per-user Run registry key
(HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run). No admin
rights required since it's scoped to the current user."""

import os
import sys
from utils.logger import logger

RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "MemUseLog"

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))


def _get_command() -> str:
    """Build the command line used to relaunch the app on login."""
    if getattr(sys, "frozen", False):
        # Packaged (e.g. PyInstaller) executable.
        return f'"{sys.executable}"'

    # Running from source: prefer pythonw.exe so no console window pops up.
    python_dir = os.path.dirname(sys.executable)
    pythonw = os.path.join(python_dir, "pythonw.exe")
    interpreter = pythonw if os.path.exists(pythonw) else sys.executable
    run_py = os.path.join(PROJECT_ROOT, "run.py")
    return f'"{interpreter}" "{run_py}"'


def is_enabled() -> bool:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_READ) as key:
            winreg.QueryValueEx(key, APP_NAME)
            return True
    except (FileNotFoundError, OSError):
        return False
    except Exception as e:
        logger.error(f"autostart.is_enabled failed: {e}")
        return False


def enable() -> bool:
    try:
        import winreg
        command = _get_command()
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, command)
        return True
    except Exception as e:
        logger.error(f"autostart.enable failed: {e}")
        return False


def disable() -> bool:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_SET_VALUE) as key:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass
        return True
    except Exception as e:
        logger.error(f"autostart.disable failed: {e}")
        return False


def set_enabled(enabled: bool) -> bool:
    return enable() if enabled else disable()
