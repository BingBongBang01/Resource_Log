"""Windows "start on boot" support via the per-user Run registry key
(HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run). No admin
rights required since it's scoped to the current user."""

import os
import sys
from utils.logger import logger
from utils.paths import PROJECT_ROOT

RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "MemUseLog"


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


def current_command():
    """What Windows will actually run at login, or None if not registered."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_READ) as key:
            value, _ = winreg.QueryValueEx(key, APP_NAME)
            return value
    except (FileNotFoundError, OSError):
        return None
    except Exception as e:
        logger.error(f"autostart.current_command failed: {e}")
        return None


def is_enabled() -> bool:
    return current_command() is not None


def refresh() -> bool:
    """Re-point an existing login entry at wherever this app now lives.

    Moving the executable — as the switch from the onedir build to the
    single-file build does — would otherwise leave Windows launching a
    path that no longer exists, and the user would only find out the next
    time they rebooted. Does nothing if autostart was never enabled.

    Packaged builds only: running from source is a development action and
    must not quietly steal the boot entry from the installed executable.
    """
    if not getattr(sys, "frozen", False):
        return False

    existing = current_command()
    if existing is None:
        return False

    wanted = _get_command()
    if existing == wanted:
        return False

    logger.info(f"Startup entry moved; updating {existing} -> {wanted}")
    return enable()


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
