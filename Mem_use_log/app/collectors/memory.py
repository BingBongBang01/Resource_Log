import psutil
import time
import ctypes
from ctypes import c_uint64, c_uint32
from .base import BaseCollector
from typing import Dict, Any

class MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [
        ('dwLength', c_uint32),
        ('dwMemoryLoad', c_uint32),
        ('ullTotalPhys', c_uint64),
        ('ullAvailPhys', c_uint64),
        ('ullTotalPageFile', c_uint64),
        ('ullAvailPageFile', c_uint64),
        ('ullTotalVirtual', c_uint64),
        ('ullAvailVirtual', c_uint64),
        ('ullAvailExtendedVirtual', c_uint64),
    ]

class MemoryCollector(BaseCollector):
    # psutil.swap_memory() costs ~39ms on Windows — more than every other
    # part of this collector combined — while pagefile size and usage move
    # very slowly. Sampling it once every 30s keeps the loop cheap.
    PAGEFILE_REFRESH_SEC = 30

    def __init__(self):
        self._last_pagefile_time = 0.0
        self._cached_pagefile = (None, None, None)

    def _get_pagefile(self):
        now = time.monotonic()
        if now - self._last_pagefile_time >= self.PAGEFILE_REFRESH_SEC:
            try:
                swap = psutil.swap_memory()
                self._cached_pagefile = (swap.total, swap.used, swap.percent)
            except Exception:
                self._cached_pagefile = (None, None, None)
            self._last_pagefile_time = now
        return self._cached_pagefile

    def collect(self) -> Dict[str, Any]:
        gb = 1024 ** 3

        # 1. Physical Memory
        mem = psutil.virtual_memory()
        
        # 2. Commit Memory (using GlobalMemoryStatusEx for exact Windows metrics)
        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        success = ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
        
        if success:
            commit_limit = stat.ullTotalPageFile
            commit_avail = stat.ullAvailPageFile
            commit_used = commit_limit - commit_avail
            commit_percent = (commit_used / commit_limit) * 100.0 if commit_limit > 0 else 0.0
        else:
            from utils.logger import logger
            logger.error("GlobalMemoryStatusEx failed.")
            commit_limit, commit_used, commit_percent = None, None, None
        
        # 3. Page File (cached; see PAGEFILE_REFRESH_SEC)
        pagefile_total, pagefile_used, pagefile_percent = self._get_pagefile()

        data = {
            # Physical
            "ram_total": round(mem.total / gb, 2),
            "ram_used": round(mem.used / gb, 2),
            "ram_available": round(mem.available / gb, 2),
            "ram_usage_percent": mem.percent,
            
            # Commit
            "commit_limit": round(commit_limit / gb, 2) if commit_limit is not None else None,
            "commit_used": round(commit_used / gb, 2) if commit_used is not None else None,
            "commit_usage_percent": round(commit_percent, 1) if commit_percent is not None else None,
            
            # Page File
            "pagefile_total": round(pagefile_total / gb, 2) if pagefile_total is not None else None,
            "pagefile_used": round(pagefile_used / gb, 2) if pagefile_used is not None else None,
            "pagefile_usage_percent": pagefile_percent
        }
        return data
