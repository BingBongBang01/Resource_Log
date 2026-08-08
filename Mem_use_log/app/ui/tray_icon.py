"""Notification-area (system tray) icon.

Built on pywin32 rather than a new dependency: Shell_NotifyIcon needs a
window to deliver its callbacks to, and this app already runs a pywin32
message-pump thread for shutdown handling, so the machinery is familiar.

Why it exists: this is a background logger. Quitting when the window is
closed threw away whatever recording was in progress, which is exactly
what the user was trying to keep. Closing now hides here instead.

Menu actions are handed back through a queue rather than called directly —
Tkinter must only be touched from the thread that created it, and this
class lives on its own thread.
"""

import queue
import sys
import threading

from i18n import t
from utils.logger import logger

ID_SHOW = 1023
ID_QUIT = 1024


class TrayIcon:
    def __init__(self, tooltip: str, on_show, on_quit):
        self.tooltip = tooltip
        self.on_show = on_show
        self.on_quit = on_quit

        self.hwnd = None
        self._hicon = None
        self._wm_trayicon = None
        self._taskbar_created = None
        self._actions = queue.Queue()
        self._ready = threading.Event()
        self._added = False

    # -- public API, called from the GUI thread -----------------------------

    def start(self) -> bool:
        """Create the icon. False means the tray is unavailable and the
        caller should keep its old quit-on-close behaviour."""
        threading.Thread(target=self._run, name="TrayIcon", daemon=True).start()
        self._ready.wait(timeout=5.0)
        return self._added

    def poll(self):
        """Run whatever the tray menu asked for. Call from the GUI thread."""
        while True:
            try:
                action = self._actions.get_nowait()
            except queue.Empty:
                return
            try:
                action()
            except Exception:
                logger.exception("Tray menu action failed")

    def stop(self):
        """Take the icon out of the tray. Called on the way out, so it must
        never raise — a dead icon is not worth blocking the exit over."""
        try:
            import win32con
            import win32gui
            self._remove_icon()
            if self.hwnd:
                # DefWindowProc turns WM_CLOSE into DestroyWindow, which ends
                # the PumpMessages loop on the tray thread.
                win32gui.PostMessage(self.hwnd, win32con.WM_CLOSE, 0, 0)
        except Exception:
            logger.exception("Removing the tray icon failed")

    # -- everything below runs on the tray thread ---------------------------

    def _run(self):
        # Imports included: a windowed build has no stderr, so an exception
        # escaping this thread would vanish without a trace.
        try:
            self._pump()
        except Exception:
            logger.exception("Tray icon unavailable; the window will quit on close instead")
        finally:
            self._ready.set()

    def _pump(self):
        import win32api
        import win32con
        import win32gui

        self._wm_trayicon = win32con.WM_USER + 20
        # Explorer restarting wipes every tray icon; this message is how it
        # tells applications to put theirs back.
        self._taskbar_created = win32gui.RegisterWindowMessage("TaskbarCreated")

        wc = win32gui.WNDCLASS()
        wc.hInstance = win32api.GetModuleHandle(None)
        wc.lpszClassName = "MemUseLogTrayIcon"
        wc.lpfnWndProc = {
            self._wm_trayicon: self._on_tray_event,
            win32con.WM_COMMAND: self._on_command,
            win32con.WM_DESTROY: self._on_destroy,
            self._taskbar_created: self._on_taskbar_created,
        }
        class_atom = win32gui.RegisterClass(wc)
        self.hwnd = win32gui.CreateWindow(
            class_atom, "Mem_use_log tray", 0, 0, 0, 0, 0, 0, 0, wc.hInstance, None,
        )

        self._hicon = self._load_icon()
        self._add_icon()
        logger.info(f"Tray icon created (hwnd {self.hwnd}).")
        self._ready.set()

        win32gui.PumpMessages()

    def _load_icon(self):
        """Use the app's own icon so the tray matches the taskbar."""
        import win32con
        import win32gui
        try:
            large, small = win32gui.ExtractIconEx(sys.executable, 0)
            chosen, spare = (small, large) if small else (large, small)
            if chosen:
                for handle in spare:
                    win32gui.DestroyIcon(handle)
                for handle in chosen[1:]:
                    win32gui.DestroyIcon(handle)
                return chosen[0]
        except Exception:
            logger.exception("Could not read the app icon; using the stock one")
        return win32gui.LoadIcon(0, win32con.IDI_APPLICATION)

    def _add_icon(self):
        import win32gui
        flags = win32gui.NIF_ICON | win32gui.NIF_MESSAGE | win32gui.NIF_TIP
        nid = (self.hwnd, 0, flags, self._wm_trayicon, self._hicon, self.tooltip)
        try:
            win32gui.Shell_NotifyIcon(win32gui.NIM_ADD, nid)
        except Exception:
            # Already present (e.g. a duplicate TaskbarCreated) — update it.
            win32gui.Shell_NotifyIcon(win32gui.NIM_MODIFY, nid)
        self._added = True

    def _remove_icon(self):
        import win32gui
        if not self._added:
            return
        self._added = False
        try:
            win32gui.Shell_NotifyIcon(win32gui.NIM_DELETE, (self.hwnd, 0))
        except Exception:
            pass

    def _on_taskbar_created(self, hwnd, msg, wparam, lparam):
        self._added = False
        self._add_icon()
        return 0

    def _on_tray_event(self, hwnd, msg, wparam, lparam):
        import win32con
        if lparam in (win32con.WM_LBUTTONUP, win32con.WM_LBUTTONDBLCLK):
            self._actions.put(self.on_show)
        elif lparam == win32con.WM_RBUTTONUP:
            self._show_menu()
        return 0

    def _on_command(self, hwnd, msg, wparam, lparam):
        import win32api
        command = win32api.LOWORD(wparam)
        if command == ID_SHOW:
            self._actions.put(self.on_show)
        elif command == ID_QUIT:
            self._actions.put(self.on_quit)
        return 0

    def _on_destroy(self, hwnd, msg, wparam, lparam):
        import win32gui
        self._remove_icon()
        win32gui.PostQuitMessage(0)
        return 0

    def _show_menu(self):
        import win32con
        import win32gui

        menu = win32gui.CreatePopupMenu()
        win32gui.AppendMenu(menu, win32con.MF_STRING, ID_SHOW, t("tray_show"))
        win32gui.AppendMenu(menu, win32con.MF_SEPARATOR, 0, "")
        win32gui.AppendMenu(menu, win32con.MF_STRING, ID_QUIT, t("tray_quit"))

        x, y = win32gui.GetCursorPos()
        # Without the foreground/WM_NULL pair the menu refuses to close when
        # the user clicks away from it — a documented Shell_NotifyIcon quirk.
        win32gui.SetForegroundWindow(self.hwnd)
        win32gui.TrackPopupMenu(
            menu, win32con.TPM_LEFTALIGN | win32con.TPM_RIGHTBUTTON, x, y, 0, self.hwnd, None,
        )
        win32gui.PostMessage(self.hwnd, win32con.WM_NULL, 0, 0)
        win32gui.DestroyMenu(menu)
