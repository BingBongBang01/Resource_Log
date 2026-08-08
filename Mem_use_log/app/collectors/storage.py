import psutil
import time
from .base import BaseCollector
from typing import Dict, Any, List

class StorageCollector(BaseCollector):
    def __init__(self):
        # We need to track IO counters per disk to calculate speeds
        self.last_io = psutil.disk_io_counters(perdisk=True)
        self.last_time = time.time()
        self.last_capacity_time = 0
        self.cached_capacity = []

    def collect(self) -> Dict[str, Any]:
        current_io = psutil.disk_io_counters(perdisk=True)
        current_time = time.time()
        
        time_delta = current_time - self.last_time
        if time_delta == 0:
            time_delta = 1
            
        mb = 1024 * 1024
        gb = 1024 ** 3
        
        now_mono = time.monotonic()
        # Capacity is only re-read once a minute. Emitting the cached rows on
        # every cycle in between would write the same free/total numbers over
        # and over, so they're only included on the cycles that refresh them.
        capacity_refreshed = False
        if now_mono - self.last_capacity_time >= 60:
            capacity_refreshed = True
            self.cached_capacity = []
            # 1. Collect Logical Drives (C:, D:, etc.) for capacity
            partitions = psutil.disk_partitions(all=False)
            for part in partitions:
                try:
                    usage = psutil.disk_usage(part.mountpoint)
                    self.cached_capacity.append({
                        "name": part.mountpoint,
                        "type": "Logical",
                        "read_mbps": None,
                        "write_mbps": None,
                        "free_gb": round(usage.free / gb, 2),
                        "total_gb": round(usage.total / gb, 2)
                    })
                except Exception:
                    pass
            self.last_capacity_time = now_mono
            
        # 2. Collect Physical Drives (PhysicalDrive0, etc.) for I/O speed
        io_rows = []
        if current_io:
            for disk_name, io_counters in current_io.items():
                last_disk_io = self.last_io.get(disk_name)
                if last_disk_io:
                    read_bytes = io_counters.read_bytes - last_disk_io.read_bytes
                    write_bytes = io_counters.write_bytes - last_disk_io.write_bytes

                    io_rows.append({
                        "name": disk_name,
                        "type": "Physical",
                        "read_mbps": round((read_bytes / mb) / time_delta, 2),
                        "write_mbps": round((write_bytes / mb) / time_delta, 2),
                        "free_gb": None,
                        "total_gb": None
                    })

        self.last_io = current_io
        self.last_time = current_time

        # "disks" is everything worth showing; "new_rows" is only what carries
        # information not already on disk, so capacity isn't re-logged every
        # cycle at the same values.
        return {
            "disks": list(self.cached_capacity) + io_rows,
            "new_rows": (list(self.cached_capacity) if capacity_refreshed else []) + io_rows,
        }
