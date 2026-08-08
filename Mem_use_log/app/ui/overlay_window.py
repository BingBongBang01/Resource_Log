"""Borderless always-on-top overlay showing selected metrics in a screen corner.

Two Windows-specific details make this usable over a game rather than just
on top of it:

  WS_EX_NOACTIVATE  the overlay never takes focus, so clicking near it (or
                    it appearing) can't alt-tab the player out of a game.
  WS_EX_TRANSPARENT mouse input passes straight through to whatever is
                    underneath, so it can't block a click in-game.

Limitation worth knowing: this is an ordinary top-level window, so it draws
over borderless-windowed and windowed games only. A game running in true
exclusive fullscreen owns the display surface and nothing but a graphics-API
hook (RTSS's own overlay, Steam, etc.) can draw on it.
"""

import ctypes
import customtkinter as ctk

from config.settings import config, OVERLAY_ITEM_ORDER
from i18n import t
from utils.logger import logger

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080  # keeps it out of the alt-tab list

# Items that only make sense while a game is being measured.
FPS_ITEMS = ("fps", "fps_avg", "fps_min", "fps_max", "frame_time")


class OverlayWindow(ctk.CTkToplevel):
    def __init__(self, master):
        super().__init__(master)

        self.withdraw()  # stay hidden until the first real update
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        try:
            self.attributes("-alpha", config.OVERLAY_OPACITY)
        except Exception:
            pass
        self.configure(fg_color="#101014")

        self._rows = {}
        self._body = ctk.CTkFrame(self, fg_color="#101014", corner_radius=8)
        self._body.pack(padx=0, pady=0)

        self._styles_applied = False
        self._visible = False
        self.after(50, self._apply_click_through)

    # --- window styling -------------------------------------------------

    def _apply_click_through(self):
        """Set the extended styles once the native window actually exists."""
        if self._styles_applied:
            return
        try:
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id()) or self.winfo_id()
            user32 = ctypes.windll.user32
            current = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            user32.SetWindowLongW(
                hwnd, GWL_EXSTYLE,
                current | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW,
            )
            self._styles_applied = True
        except Exception:
            # Worst case it behaves like a normal always-on-top window.
            logger.exception("Could not apply click-through styles to the overlay")
            self._styles_applied = True

    def _reposition(self):
        """Pin to the configured corner of the primary screen."""
        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        m = config.OVERLAY_MARGIN

        position = config.OVERLAY_POSITION
        x = sw - w - m if position.endswith("right") else m
        y = sh - h - m if position.startswith("bottom") else m
        self.geometry(f"+{max(0, x)}+{max(0, y)}")

    # --- content --------------------------------------------------------

    def _ensure_row(self, key: str):
        row = self._rows.get(key)
        if row is None:
            row = ctk.CTkLabel(
                self._body, text="", anchor="w", justify="left",
                font=("Consolas", 13, "bold"), text_color="#F2F2F2",
            )
            self._rows[key] = row
        return row

    def render(self, values: dict, game_active: bool):
        """values maps item key -> already-formatted string (or None)."""
        if not config.OVERLAY_ENABLED:
            self.hide()
            return

        shown = 0
        for key in OVERLAY_ITEM_ORDER:
            row = self._ensure_row(key)

            wanted = config.OVERLAY_ITEMS.get(key, False)
            # FPS rows are only meaningful while something is presenting frames.
            if key in FPS_ITEMS and not game_active:
                wanted = False

            text = values.get(key) if wanted else None
            if text is None:
                row.pack_forget()
                continue

            row.configure(text=text)
            row.pack(anchor="w", padx=10, pady=1)
            shown += 1

        if not shown:
            self.hide()
            return

        if not self._visible:
            self.deiconify()
            self.attributes("-topmost", True)
            self._visible = True
        self._apply_click_through()
        self._reposition()

    def hide(self):
        if self._visible:
            self.withdraw()
            self._visible = False

    def set_opacity(self, value: float):
        try:
            self.attributes("-alpha", value)
        except Exception:
            pass
