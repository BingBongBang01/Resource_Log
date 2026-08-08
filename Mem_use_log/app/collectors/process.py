import psutil
from .base import BaseCollector
from typing import Dict, Any, List


class ProcessCollector(BaseCollector):
    # Kernel bookkeeping pseudo-processes, not real workloads. "System Idle
    # Process" in particular accounts for all *unused* CPU time, so it always
    # tops the list and would crowd out every genuine CPU consumer.
    PSEUDO_PROCESS_PIDS = {0}
    PSEUDO_PROCESS_NAMES = {"system idle process", "idle"}

    def __init__(self):
        # Warmup for CPU calculation: first call establishes the baseline
        for proc in psutil.process_iter(['cpu_percent']):
            pass
        self.cpu_count = psutil.cpu_count() or 1

    def collect(self) -> Dict[str, List[Dict[str, Any]]]:
        processes = []

        # Iterate over all running processes
        for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_info']):
            try:
                # cpu_percent might be 0.0 on first call without interval, but we can't wait for all
                # psutil allows calling cpu_percent() without interval, which compares to last call
                info = proc.info
                pid = info.get('pid', 0)
                name = info.get('name', 'Unknown') or 'Unknown'

                if pid in self.PSEUDO_PROCESS_PIDS or name.lower() in self.PSEUDO_PROCESS_NAMES:
                    continue

                # psutil reports per-process CPU as a share of a single core,
                # so it reaches 100 * core_count on a fully loaded machine.
                # Normalize to a whole-system percentage to match Task Manager.
                cpu = (info.get('cpu_percent', 0.0) or 0.0) / self.cpu_count
                mem_info = info.get('memory_info')
                ram_mb = mem_info.rss / (1024 * 1024) if mem_info else 0.0

                processes.append({
                    'pid': pid,
                    'name': name,
                    'cpu_percent': round(cpu, 2),
                    'ram_mb': round(ram_mb, 2)
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass

        # Sort for top CPU
        top_cpu = sorted(processes, key=lambda p: p['cpu_percent'], reverse=True)[:10]
        
        # Sort for top RAM
        top_ram = sorted(processes, key=lambda p: p['ram_mb'], reverse=True)[:10]
        
        # GPU is not easily available via psutil, skip for now or set empty
        top_gpu = []
        
        return {
            "top_cpu": top_cpu,
            "top_ram": top_ram,
            "top_gpu": top_gpu
        }
