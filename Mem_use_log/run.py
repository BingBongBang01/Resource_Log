import sys
import os

# Add app to path so imports work correctly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'app')))

from scheduler.collector_loop import CollectorLoop
from ui.app_window import AppWindow

_MUTEX_NAME = "Global\\MemUseLog_SingleInstance_Mutex"
_mutex_handle = None


def _acquire_single_instance_lock() -> bool:
    """Prevent two OS processes (e.g. a manual launch on top of the
    Windows-boot autostart launch) from both running a CollectorLoop against
    the same SQLite database at once. Returns False if another instance
    already holds the lock."""
    global _mutex_handle
    try:
        import win32event
        import win32api
        import winerror
        _mutex_handle = win32event.CreateMutex(None, False, _MUTEX_NAME)
        already_running = win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS
        return not already_running
    except Exception:
        # pywin32 not available for some reason; don't block startup over it.
        return True


def main():
    if not _acquire_single_instance_lock():
        print("Mem_use_log is already running. Exiting this instance.")
        return

    print("Initializing Collector Loop...")
    collector_loop = CollectorLoop()

    print("Starting GUI...")
    app = AppWindow(collector_loop)

    # Run the GUI main loop
    try:
        app.mainloop()
    except KeyboardInterrupt:
        pass
    finally:
        collector_loop.stop()

if __name__ == "__main__":
    main()
