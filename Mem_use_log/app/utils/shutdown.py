"""Funnels every way this process can end into one save-the-logs handler.

Tkinter only gives us a clean exit when the user closes the window. A
Windows shutdown/logoff, a Ctrl+C, or an unhandled exception all bypass
that path, and whatever the SQLite writer still had buffered would go
with them. Each of those routes is wired to the same handler here,
guarded so it can only ever run once no matter how many fire at the
same time.

The one case nothing can cover is a hard kill (Task Manager "End task",
power loss) — Windows terminates the process without notice, so only
data already committed to the database survives.
"""

import atexit
import signal
import sys
import threading

from utils.logger import logger

# Windows only gives an app a few seconds once it has answered
# WM_QUERYENDSESSION, so the shutdown path gets a tighter budget than a
# leisurely user-initiated close.
NORMAL_BUDGET = 15.0
URGENT_BUDGET = 6.0

_lock = threading.Lock()
_finished = False
_handler = None


def register(handler):
    """Install `handler(reason: str, budget: float)` on every exit path."""
    global _handler
    _handler = handler

    atexit.register(run_now, "atexit")
    _install_signal_handlers()
    _start_session_end_watcher()


def run_now(reason: str, budget: float = NORMAL_BUDGET) -> None:
    """Run the save handler unless some other exit path already did."""
    global _finished
    with _lock:
        if _finished or _handler is None:
            return
        _finished = True

    logger.info(f"Shutdown ({reason}): saving logs...")
    try:
        _handler(reason, budget)
        logger.info(f"Shutdown ({reason}): logs saved.")
    except Exception:
        logger.exception(f"Shutdown ({reason}): saving logs failed")


def _install_signal_handlers():
    def _on_signal(signum, frame):
        run_now(f"signal {signum}", URGENT_BUDGET)
        sys.exit(0)

    # SIGBREAK is Windows-only; SIGTERM exists but is only raised by an
    # explicit kill. Registering fails outside the main thread, which is
    # not fatal — the other hooks still cover us.
    for name in ("SIGINT", "SIGTERM", "SIGBREAK"):
        sig = getattr(signal, name, None)
        if sig is None:
            continue
        try:
            signal.signal(sig, _on_signal)
        except (ValueError, OSError):
            pass


def _start_session_end_watcher():
    """Listen for Windows shutdown/logoff on a hidden top-level window.

    Only a real top-level window receives WM_QUERYENDSESSION — a
    message-only window is skipped by the broadcast — so this one is
    created without WS_VISIBLE rather than made message-only.
    """
    try:
        import win32con  # noqa: F401  (probe pywin32 before spawning a thread)
    except Exception:
        logger.warning("pywin32 unavailable; logs will not be saved on Windows shutdown.")
        return

    threading.Thread(target=_session_end_loop, name="ShutdownWatcher", daemon=True).start()


def _session_end_loop():
    import win32api
    import win32con
    import win32gui

    def _save(hwnd):
        # Ask Windows not to kill us mid-write. The reason is dropped again
        # as soon as the flush is done so the shutdown UI never stalls on us.
        blocked = _block_shutdown(hwnd)
        try:
            run_now("system-shutdown", URGENT_BUDGET)
        finally:
            if blocked:
                _unblock_shutdown(hwnd)

    def _on_query_end_session(hwnd, msg, wparam, lparam):
        _save(hwnd)
        return 1  # TRUE: we are ready, go ahead and shut down

    def _on_end_session(hwnd, msg, wparam, lparam):
        if wparam:
            _save(hwnd)
        return 0

    try:
        wc = win32gui.WNDCLASS()
        wc.hInstance = win32api.GetModuleHandle(None)
        wc.lpszClassName = "MemUseLogShutdownWatcher"
        wc.lpfnWndProc = {
            win32con.WM_QUERYENDSESSION: _on_query_end_session,
            win32con.WM_ENDSESSION: _on_end_session,
        }
        class_atom = win32gui.RegisterClass(wc)
        win32gui.CreateWindow(
            class_atom, "Mem_use_log shutdown watcher",
            0, 0, 0, 0, 0, 0, 0, wc.hInstance, None,
        )
        win32gui.PumpMessages()
    except Exception:
        logger.exception("Shutdown watcher stopped; logs may be lost on Windows shutdown")


def _block_shutdown(hwnd) -> bool:
    try:
        import ctypes
        return bool(ctypes.windll.user32.ShutdownBlockReasonCreate(
            ctypes.c_void_p(hwnd), ctypes.c_wchar_p("Saving resource logs...")))
    except Exception:
        return False


def _unblock_shutdown(hwnd) -> None:
    try:
        import ctypes
        ctypes.windll.user32.ShutdownBlockReasonDestroy(ctypes.c_void_p(hwnd))
    except Exception:
        pass
