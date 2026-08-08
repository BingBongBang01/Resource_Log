import psutil
import time
import threading
from .base import BaseCollector
from typing import Dict, Any
from providers.cpu_temp_provider import get_cpu_temp_provider

class CPUCollector(BaseCollector):
    def __init__(self):
        # psutil cpu_percent requires a first call to baseline
        psutil.cpu_percent(interval=None)
        # The temperature providers hold WMI/COM objects, which are bound to
        # the thread that created them. Building one here (main thread) and
        # calling it from the collector thread fails with RPC_E_WRONG_THREAD,
        # so bind it lazily to whichever thread actually collects.
        self._local = threading.local()
        self.last_temp_time = 0
        self.cached_temp = None

    def _get_temp_provider(self):
        provider = getattr(self._local, "provider", None)
        if provider is None:
            provider = get_cpu_temp_provider()
            self._local.provider = provider
        return provider

    def collect(self) -> Dict[str, Any]:
        now = time.monotonic()
        if now - self.last_temp_time >= 15:
            self.cached_temp, _ = self._get_temp_provider().get_temperature()
            self.last_temp_time = now

        try:
            freq = psutil.cpu_freq().current
        except Exception:
            freq = 0.0

        data = {
            "cpu_usage": psutil.cpu_percent(interval=None),
            "cpu_temperature": self.cached_temp,
            "cpu_freq_mhz": freq
        }
        
        return data
