"""Per-application FPS via RivaTuner Statistics Server (RTSS).

Windows gives no way for one process to measure another's frame rate on its
own — it takes either a graphics-API hook or an ETW trace. RTSS (shipped with
MSI Afterburner, and free standalone) already hooks games and publishes their
frame statistics into a shared-memory block, so reading it is the cheapest
and safest route: read-only, no admin rights, no injection by us.

Shared memory layout (RTSSSharedMemoryV2), from RTSS's own SDK headers:

    RTSS_SHARED_MEMORY            header
        dwSignature               'RTSS'
        dwVersion                 >= 0x00020000
        dwAppEntrySize            size of one app entry
        dwAppArrOffset            offset to the app entry array
        dwAppArrSize              number of entries
        ...
    RTSS_SHARED_MEMORY_APP_ENTRY  per hooked application
        szName[MAX_PATH]          process path
        dwProcessID
        ...
        dwTime0, dwTime1          frame-time window boundaries (ms)
        dwFrames                  frames presented in that window
        dwFrameTime               last frame time, microseconds

Instantaneous FPS is dwFrames / ((dwTime1 - dwTime0) / 1000), which is what
RTSS's own overlay displays. Min/max/average are accumulated on our side
across samples, since the shared block only carries the current window.
"""

import ctypes
import os
import time
from ctypes import wintypes
from typing import Dict, Any, List, Optional

from utils.logger import logger

MAX_PATH = 260

FILE_MAP_READ = 0x0004
RTSS_SIGNATURE = 0x53535452  # 'RTSS' little-endian


class _RTSS_SHARED_MEMORY(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ("dwSignature", ctypes.c_uint32),
        ("dwVersion", ctypes.c_uint32),
        ("dwAppEntrySize", ctypes.c_uint32),
        ("dwAppArrOffset", ctypes.c_uint32),
        ("dwAppArrSize", ctypes.c_uint32),
        ("dwOSDEntrySize", ctypes.c_uint32),
        ("dwOSDArrOffset", ctypes.c_uint32),
        ("dwOSDArrSize", ctypes.c_uint32),
        ("dwOSDFrame", ctypes.c_uint32),
    ]


class _RTSS_APP_ENTRY(ctypes.Structure):
    """Only the leading fields are declared: everything we need lives near the
    start, and dwAppEntrySize from the header is used for striding so trailing
    fields we don't model can't throw the offsets off."""
    _pack_ = 1
    _fields_ = [
        ("szName", ctypes.c_char * MAX_PATH),
        ("dwProcessID", ctypes.c_uint32),
        ("dwFlags", ctypes.c_uint32),
        ("dwTime0", ctypes.c_uint32),
        ("dwTime1", ctypes.c_uint32),
        ("dwFrames", ctypes.c_uint32),
        ("dwFrameTime", ctypes.c_uint32),
    ]


class FPSStats:
    """Rolling frame statistics for one application."""

    def __init__(self, name: str, pid: int):
        self.name = name
        self.pid = pid
        self.current_fps: Optional[float] = None
        self.frame_time_ms: Optional[float] = None
        self.min_fps: Optional[float] = None
        self.max_fps: Optional[float] = None
        self._fps_sum = 0.0
        self._fps_count = 0
        self._seen = 0

    @property
    def avg_fps(self) -> Optional[float]:
        if not self._fps_count:
            return None
        return round(self._fps_sum / self._fps_count, 1)

    def add_sample(self, fps: Optional[float], frame_time_ms: Optional[float]):
        self.frame_time_ms = frame_time_ms
        if fps is None or fps <= 0:
            return
        self.current_fps = fps
        self._seen += 1
        # Discard the first sample outright — right after RTSS attaches its
        # hook the measurement window is partial and reports an unrealistic
        # spike, which would skew the average as badly as the min/max.
        if self._seen == 1:
            return
        self._fps_sum += fps
        self._fps_count += 1
        self.min_fps = fps if self.min_fps is None else min(self.min_fps, fps)
        self.max_fps = fps if self.max_fps is None else max(self.max_fps, fps)

    def reset(self):
        self.current_fps = None
        self.frame_time_ms = None
        self.min_fps = None
        self.max_fps = None
        self._fps_sum = 0.0
        self._fps_count = 0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "pid": self.pid,
            "fps": round(self.current_fps, 1) if self.current_fps is not None else None,
            "fps_avg": self.avg_fps,
            "fps_min": round(self.min_fps, 1) if self.min_fps is not None else None,
            "fps_max": round(self.max_fps, 1) if self.max_fps is not None else None,
            "frame_time_ms": round(self.frame_time_ms, 2) if self.frame_time_ms is not None else None,
        }


class RTSSProvider:
    """Reads RTSS's shared memory. Safe to construct when RTSS isn't running;
    `available` just stays False and every read returns nothing."""

    def __init__(self):
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._kernel32.OpenFileMappingW.restype = wintypes.HANDLE
        self._kernel32.OpenFileMappingW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
        self._kernel32.MapViewOfFile.restype = ctypes.c_void_p
        self._kernel32.MapViewOfFile.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                                 wintypes.DWORD, wintypes.DWORD, ctypes.c_size_t]
        self._kernel32.UnmapViewOfFile.argtypes = [ctypes.c_void_p]
        self._kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

        self._handle = None
        self._view = None
        self._stats: Dict[int, FPSStats] = {}
        self._last_frames: Dict[int, tuple] = {}

    @property
    def available(self) -> bool:
        return self._view is not None

    def _open(self) -> bool:
        """Attach to the shared block. RTSS creates it on start and destroys
        it on exit, so this is retried rather than done once."""
        if self._view is not None:
            return True
        try:
            handle = self._kernel32.OpenFileMappingW(FILE_MAP_READ, False, "RTSSSharedMemoryV2")
            if not handle:
                return False
            view = self._kernel32.MapViewOfFile(handle, FILE_MAP_READ, 0, 0, 0)
            if not view:
                self._kernel32.CloseHandle(handle)
                return False

            header = ctypes.cast(view, ctypes.POINTER(_RTSS_SHARED_MEMORY)).contents
            if header.dwSignature != RTSS_SIGNATURE:
                # Not RTSS, or a layout we don't understand — don't read on.
                self._kernel32.UnmapViewOfFile(ctypes.c_void_p(view))
                self._kernel32.CloseHandle(handle)
                return False

            self._handle = handle
            self._view = view
            logger.info(f"RTSS shared memory attached (version 0x{header.dwVersion:08X})")
            return True
        except Exception:
            logger.exception("Failed to open RTSS shared memory")
            return False

    def close(self):
        try:
            if self._view:
                self._kernel32.UnmapViewOfFile(ctypes.c_void_p(self._view))
            if self._handle:
                self._kernel32.CloseHandle(self._handle)
        except Exception:
            pass
        self._view = None
        self._handle = None

    def _detach(self):
        """RTSS went away; drop the mapping so the next poll can reattach."""
        self.close()
        self._stats.clear()
        self._last_frames.clear()

    def get_apps(self) -> List[Dict[str, Any]]:
        """Every application RTSS currently reports frames for."""
        if not self._open():
            return []

        try:
            header = ctypes.cast(self._view, ctypes.POINTER(_RTSS_SHARED_MEMORY)).contents
            if header.dwSignature != RTSS_SIGNATURE:
                self._detach()
                return []

            entry_size = header.dwAppEntrySize
            base = self._view + header.dwAppArrOffset
            live_pids = set()
            results = []

            for i in range(header.dwAppArrSize):
                entry = ctypes.cast(base + i * entry_size,
                                    ctypes.POINTER(_RTSS_APP_ENTRY)).contents
                pid = entry.dwProcessID
                if not pid:
                    continue

                dt_ms = entry.dwTime1 - entry.dwTime0
                frames = entry.dwFrames
                # A stale entry keeps its last window; only treat it as live
                # when the frame counter or window actually moved.
                signature = (entry.dwTime0, entry.dwTime1, frames)
                if self._last_frames.get(pid) == signature and frames == 0:
                    continue
                self._last_frames[pid] = signature

                fps = (frames * 1000.0 / dt_ms) if dt_ms > 0 and frames > 0 else None
                frame_time_ms = entry.dwFrameTime / 1000.0 if entry.dwFrameTime else None

                if fps is None and frame_time_ms is None:
                    continue

                name = os.path.basename((entry.szName or b"").decode("utf-8", "ignore")) or f"pid {pid}"
                stats = self._stats.get(pid)
                if stats is None or stats.name != name:
                    stats = FPSStats(name, pid)
                    self._stats[pid] = stats
                stats.add_sample(fps, frame_time_ms)

                live_pids.add(pid)
                results.append(stats.as_dict())

            # Forget applications that have exited so their min/max don't
            # bleed into the next game that reuses the PID.
            for pid in list(self._stats):
                if pid not in live_pids:
                    self._stats.pop(pid, None)
                    self._last_frames.pop(pid, None)

            return results
        except Exception:
            logger.exception("Error reading RTSS shared memory")
            self._detach()
            return []

    def get_active_app(self) -> Optional[Dict[str, Any]]:
        """The app most likely being played: the one presenting fastest."""
        apps = [a for a in self.get_apps() if a.get("fps")]
        if not apps:
            return None
        return max(apps, key=lambda a: a["fps"])

    def reset_stats(self):
        for stats in self._stats.values():
            stats.reset()


_provider: Optional[RTSSProvider] = None


def get_fps_provider() -> RTSSProvider:
    global _provider
    if _provider is None:
        _provider = RTSSProvider()
    return _provider
