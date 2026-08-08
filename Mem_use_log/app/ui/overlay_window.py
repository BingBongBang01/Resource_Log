"""On-screen overlay in the style of the GeForce Experience counter:
angular green digits with a black outline, pinned to a screen corner.

Why this is a native window and not a Tk toplevel:

  * Giving the text and the background *different* opacities needs
    per-pixel alpha. A Tk toplevel has one -alpha for the whole window,
    so the background could never be more transparent than the digits.
    Windows exposes per-pixel alpha only through UpdateLayeredWindow with
    a 32-bit premultiplied bitmap, which is what this pushes.
  * Drawing with Pillow gets the black outline that keeps green digits
    readable over a bright game.

The digits are drawn as seven-segment shapes rather than set in a font.
Windows ships no seven-segment typeface, and one cannot be assumed to be
installed, so drawing them keeps the look identical on every machine.

Two extended styles make it usable over a game rather than merely on top:
WS_EX_TRANSPARENT lets clicks pass through, and WS_EX_NOACTIVATE stops it
stealing focus. As an ordinary window it still cannot draw over a game in
true exclusive fullscreen — nothing but a graphics-API hook can.
"""

import ctypes
from ctypes import wintypes

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

from config.settings import config, hex_to_rgb, OVERLAY_ITEM_ORDER
from utils.logger import logger

# Items that only mean anything while something is presenting frames.
FPS_ITEMS = ("fps", "fps_avg", "fps_min", "fps_max", "frame_time")

WS_POPUP = 0x80000000
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080  # keeps it out of the alt-tab list
WS_EX_TOPMOST = 0x00000008

SW_HIDE = 0
SW_SHOWNOACTIVATE = 4
HWND_TOPMOST = ctypes.c_void_p(-1)  # a sentinel handle, not a real window
SWP_NOACTIVATE = 0x0010
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002

AC_SRC_OVER = 0x00
AC_SRC_ALPHA = 0x01
ULW_ALPHA = 0x02
SM_CXSCREEN, SM_CYSCREEN = 0, 1


_user32 = ctypes.WinDLL("user32", use_last_error=True)
_gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)


class _BLENDFUNCTION(ctypes.Structure):
    _fields_ = [("BlendOp", ctypes.c_byte), ("BlendFlags", ctypes.c_byte),
                ("SourceConstantAlpha", ctypes.c_byte), ("AlphaFormat", ctypes.c_byte)]


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class _SIZE(ctypes.Structure):
    _fields_ = [("cx", ctypes.c_long), ("cy", ctypes.c_long)]


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_int32),
                ("biHeight", ctypes.c_int32), ("biPlanes", ctypes.c_uint16),
                ("biBitCount", ctypes.c_uint16), ("biCompression", ctypes.c_uint32),
                ("biSizeImage", ctypes.c_uint32), ("biXPelsPerMeter", ctypes.c_int32),
                ("biYPelsPerMeter", ctypes.c_int32), ("biClrUsed", ctypes.c_uint32),
                ("biClrImportant", ctypes.c_uint32)]


def _bind_win32():
    """Declare every signature we call.

    Without argtypes, ctypes assumes C int for each argument and truncates
    64-bit handles — a DC passed on to CreateDIBSection raises "int too long
    to convert" rather than quietly misbehaving, but only at run time.
    """
    _user32.GetDC.argtypes = [wintypes.HWND]
    _user32.GetDC.restype = wintypes.HDC
    _user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    _user32.ReleaseDC.restype = ctypes.c_int
    _user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    _user32.ShowWindow.restype = wintypes.BOOL
    _user32.GetSystemMetrics.argtypes = [ctypes.c_int]
    _user32.GetSystemMetrics.restype = ctypes.c_int
    _user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                     ctypes.c_int, ctypes.c_int, ctypes.c_uint]
    _user32.SetWindowPos.restype = wintypes.BOOL
    _user32.UpdateLayeredWindow.argtypes = [
        wintypes.HWND, wintypes.HDC, ctypes.POINTER(_POINT), ctypes.POINTER(_SIZE),
        wintypes.HDC, ctypes.POINTER(_POINT), wintypes.COLORREF,
        ctypes.POINTER(_BLENDFUNCTION), wintypes.DWORD,
    ]
    _user32.UpdateLayeredWindow.restype = wintypes.BOOL

    _gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
    _gdi32.CreateCompatibleDC.restype = wintypes.HDC
    _gdi32.CreateDIBSection.argtypes = [wintypes.HDC, ctypes.POINTER(_BITMAPINFOHEADER),
                                        ctypes.c_uint, ctypes.POINTER(ctypes.c_void_p),
                                        wintypes.HANDLE, wintypes.DWORD]
    _gdi32.CreateDIBSection.restype = wintypes.HBITMAP
    _gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
    _gdi32.SelectObject.restype = wintypes.HGDIOBJ
    _gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    _gdi32.DeleteObject.restype = wintypes.BOOL
    _gdi32.DeleteDC.argtypes = [wintypes.HDC]
    _gdi32.DeleteDC.restype = wintypes.BOOL


_bind_win32()

# Which of the seven segments each character lights up.
#
#     aaaa
#    f    b
#    f    b
#     gggg
#    e    c
#    e    c
#     dddd
SEGMENTS = {
    "0": "abcdef", "1": "bc", "2": "abged", "3": "abgcd", "4": "fgbc",
    "5": "afgcd", "6": "afgecd", "7": "abc", "8": "abcdefg", "9": "afgbcd",
    "-": "g", ".": ".", " ": "",
}


class OverlayWindow:
    def __init__(self, master=None):
        # master is accepted so the call site reads the same as the Tk
        # toplevel this replaced; a layered window has no Tk parent.
        self._hwnd = None
        self._visible = False
        self._cache_key = None
        self._font_cache = {}
        try:
            self._create_window()
        except Exception:
            logger.exception("Overlay window could not be created; it will stay off")

    # --- native window ----------------------------------------------------

    def _create_window(self):
        import win32api
        import win32gui

        wc = win32gui.WNDCLASS()
        wc.hInstance = win32api.GetModuleHandle(None)
        wc.lpszClassName = "MemUseLogOverlay"
        wc.lpfnWndProc = {}  # DefWindowProc handles everything we get
        class_atom = win32gui.RegisterClass(wc)

        ex_style = (WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_NOACTIVATE
                    | WS_EX_TOOLWINDOW | WS_EX_TOPMOST)
        self._hwnd = win32gui.CreateWindowEx(
            ex_style, class_atom, "Mem_use_log overlay", WS_POPUP,
            0, 0, 1, 1, 0, 0, wc.hInstance, None,
        )
        # Created on the GUI thread on purpose: Tk's event loop pumps every
        # message for its own thread, so this window needs no pump of its own.
        logger.info(f"Overlay window created (hwnd {self._hwnd}).")

    # --- drawing ----------------------------------------------------------

    # Malgun Gothic first: the labels are Korean by default and Consolas has
    # no Hangul, which draws every one of them as a tofu box. Malgun covers
    # Latin too, so one font serves both languages.
    FONT_CANDIDATES = ("malgun.ttf", "segoeui.ttf", "consola.ttf", "arial.ttf")

    def _font(self, size: int):
        font = self._font_cache.get(size)
        if font is None:
            for name in self.FONT_CANDIDATES:
                try:
                    font = ImageFont.truetype(name, size)
                    break
                except Exception:
                    continue
            if font is None:
                logger.warning("No overlay font found; falling back to Pillow's bitmap font")
                font = ImageFont.load_default()
            self._font_cache[size] = font
        return font

    @staticmethod
    def _segment_polygons(x, y, w, h, thickness):
        """Corner points for each lit bar of one seven-segment cell.

        The bars are hexagons rather than rectangles so their mitred ends
        meet at the corners the way a real segment display looks.
        """
        t = thickness
        half = t / 2.0
        mid = y + h / 2.0
        right = x + w
        bottom = y + h

        def horizontal(cy):
            return [(x + half, cy - half), (right - half, cy - half), (right, cy),
                    (right - half, cy + half), (x + half, cy + half), (x, cy)]

        def vertical(cx, top, bot):
            return [(cx - half, top + half), (cx, top), (cx + half, top + half),
                    (cx + half, bot - half), (cx, bot), (cx - half, bot - half)]

        return {
            "a": horizontal(y + half),
            "d": horizontal(bottom - half),
            "g": horizontal(mid),
            "f": vertical(x + half, y, mid),
            "e": vertical(x + half, mid, bottom),
            "b": vertical(right - half, y, mid),
            "c": vertical(right - half, mid, bottom),
        }

    def _draw_digits(self, mask_draw, text: str, x: int, y: int, height: int) -> int:
        """Paint `text` into the shape mask. Returns the width used."""
        cell_w = int(height * 0.58)
        thickness = max(2, int(height * 0.16))
        gap = max(2, int(height * 0.12))
        dot_w = max(3, int(height * 0.18))

        cursor = x
        for char in text:
            if char == ".":
                r = thickness / 2.0
                cy = y + height - r
                mask_draw.ellipse([cursor, cy - r, cursor + 2 * r, cy + r], fill=255)
                cursor += dot_w + gap
                continue

            lit = SEGMENTS.get(char)
            if lit is None:
                # Anything the segment display can't spell falls back to text.
                cursor += self._draw_text_mask(mask_draw, char, cursor, y, height) + gap
                continue

            polygons = self._segment_polygons(cursor, y, cell_w, height, thickness)
            for name in lit:
                mask_draw.polygon(polygons[name], fill=255)
            cursor += cell_w + gap

        return cursor - x

    def _draw_text_mask(self, mask_draw, text: str, x: int, y: int, height: int) -> int:
        font = self._font(max(8, int(height * 0.9)))
        mask_draw.text((x, y), text, fill=255, font=font)
        return int(mask_draw.textlength(text, font=font))

    def _compose(self, rows):
        """Render the rows to an RGBA image.

        Everything is drawn into a single-channel shape mask first. The
        outline is then that mask dilated and the mask itself punched back
        out, which traces the union of the glyphs — dilating each segment
        on its own would draw seams between the bars of a digit.
        """
        size = max(8, int(config.OVERLAY_FONT_SIZE))
        text_rgb = hex_to_rgb(config.OVERLAY_TEXT_COLOR, (57, 255, 20))
        bg_rgb = hex_to_rgb(config.OVERLAY_BG_COLOR, (0, 0, 0))
        text_alpha = int(max(0.0, min(1.0, config.OVERLAY_TEXT_OPACITY)) * 255)
        bg_alpha = int(max(0.0, min(1.0, config.OVERLAY_BG_OPACITY)) * 255)

        stroke = max(1, int(size * 0.07))
        pad = stroke + max(4, size // 4)
        line_gap = max(2, size // 5)

        # Measure first so the bitmap is exactly as big as it needs to be.
        widths, heights = [], []
        for is_digits, text in rows:
            if is_digits:
                widths.append(self._measure_digits(text, size))
                heights.append(size)
            else:
                small = max(8, int(size * 0.5))
                font = self._font(small)
                widths.append(int(font.getlength(text)))
                heights.append(int(small * 1.35))

        width = max(widths) + 2 * pad
        height = sum(heights) + line_gap * (len(rows) - 1) + 2 * pad

        mask = Image.new("L", (width, height), 0)
        mask_draw = ImageDraw.Draw(mask)

        cursor_y = pad
        for (is_digits, text), row_h in zip(rows, heights):
            if is_digits:
                self._draw_digits(mask_draw, text, pad, cursor_y, size)
            else:
                small = max(8, int(size * 0.5))
                mask_draw.text((pad, cursor_y), text, fill=255, font=self._font(small))
            cursor_y += row_h + line_gap

        outline = mask.filter(ImageFilter.MaxFilter(2 * stroke + 1))
        outline = ImageChops.subtract(outline, mask)

        image = Image.new("RGBA", (width, height), bg_rgb + (bg_alpha,))
        image.paste(Image.new("RGBA", (width, height), (0, 0, 0, 255)), (0, 0), outline)
        image.paste(Image.new("RGBA", (width, height), text_rgb + (text_alpha,)), (0, 0), mask)
        return image

    def _measure_digits(self, text: str, height: int) -> int:
        cell_w = int(height * 0.58)
        gap = max(2, int(height * 0.12))
        dot_w = max(3, int(height * 0.18))
        total = 0
        for char in text:
            total += (dot_w if char == "." else cell_w) + gap
        return max(1, total - gap)

    # --- presentation -----------------------------------------------------

    def render(self, values: dict, game_active: bool):
        """values maps item key -> already-formatted string (or None)."""
        if not config.OVERLAY_ENABLED or self._hwnd is None:
            self.hide()
            return

        rows = []
        for key in OVERLAY_ITEM_ORDER:
            if not config.OVERLAY_ITEMS.get(key, False):
                continue
            if key in FPS_ITEMS and not game_active:
                continue
            text = values.get(key)
            if not text:
                continue
            # The plain frame rate gets the segment-display treatment; the
            # rest are labelled rows where words matter more than style.
            rows.append((key == "fps", text))

        if not rows:
            self.hide()
            return

        cache_key = (tuple(rows), config.OVERLAY_FONT_SIZE, config.OVERLAY_TEXT_COLOR,
                     config.OVERLAY_BG_COLOR, config.OVERLAY_TEXT_OPACITY,
                     config.OVERLAY_BG_OPACITY, config.OVERLAY_POSITION)
        if cache_key == self._cache_key:
            return
        self._cache_key = cache_key

        try:
            image = self._compose(rows)
            self._push(image)
        except Exception:
            logger.exception("Overlay draw failed")
            self.hide()

    def _push(self, image):
        w, h = image.size
        x, y = self._position(w, h)

        # UpdateLayeredWindow wants premultiplied BGRA; ImageChops.multiply
        # is exactly the (channel * alpha / 255) that premultiplying means.
        r, g, b, a = image.split()
        buf = Image.merge("RGBA", (ImageChops.multiply(b, a), ImageChops.multiply(g, a),
                                   ImageChops.multiply(r, a), a)).tobytes()

        screen_dc = _user32.GetDC(None)
        mem_dc = _gdi32.CreateCompatibleDC(screen_dc)
        bitmap = old_bitmap = None
        try:
            header = _BITMAPINFOHEADER()
            header.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
            header.biWidth = w
            header.biHeight = -h          # negative: top-down, matching PIL
            header.biPlanes = 1
            header.biBitCount = 32
            header.biCompression = 0      # BI_RGB

            bits = ctypes.c_void_p()
            bitmap = _gdi32.CreateDIBSection(mem_dc, ctypes.byref(header), 0,
                                             ctypes.byref(bits), None, 0)
            if not bitmap:
                raise OSError(f"CreateDIBSection failed ({ctypes.get_last_error()})")
            ctypes.memmove(bits, buf, len(buf))
            old_bitmap = _gdi32.SelectObject(mem_dc, bitmap)

            blend = _BLENDFUNCTION(AC_SRC_OVER, 0, 255, AC_SRC_ALPHA)
            ok = _user32.UpdateLayeredWindow(
                self._hwnd, screen_dc, ctypes.byref(_POINT(x, y)),
                ctypes.byref(_SIZE(w, h)), mem_dc, ctypes.byref(_POINT(0, 0)),
                0, ctypes.byref(blend), ULW_ALPHA,
            )
            if not ok:
                raise OSError(f"UpdateLayeredWindow failed ({ctypes.get_last_error()})")
        finally:
            if old_bitmap:
                _gdi32.SelectObject(mem_dc, old_bitmap)
            if bitmap:
                _gdi32.DeleteObject(bitmap)
            _gdi32.DeleteDC(mem_dc)
            _user32.ReleaseDC(None, screen_dc)

        if not self._visible:
            _user32.ShowWindow(self._hwnd, SW_SHOWNOACTIVATE)
            self._visible = True
        # Re-assert topmost: a game going fullscreen can push us behind it.
        _user32.SetWindowPos(self._hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                             SWP_NOACTIVATE | SWP_NOSIZE | SWP_NOMOVE)

    def _position(self, w, h):
        sw = _user32.GetSystemMetrics(SM_CXSCREEN)
        sh = _user32.GetSystemMetrics(SM_CYSCREEN)
        m = config.OVERLAY_MARGIN
        position = config.OVERLAY_POSITION
        x = sw - w - m if position.endswith("right") else m
        y = sh - h - m if position.startswith("bottom") else m
        return max(0, x), max(0, y)

    def hide(self):
        if self._visible and self._hwnd:
            _user32.ShowWindow(self._hwnd, SW_HIDE)
        self._visible = False
        self._cache_key = None

    def apply_settings(self):
        """Colours/size/opacity changed — force the next render to redraw."""
        self._cache_key = None
