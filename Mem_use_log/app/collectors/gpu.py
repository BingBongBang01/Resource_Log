import time
import threading
from .base import BaseCollector
from typing import Dict, Any
from providers.gpu_provider import get_multi_gpu_provider


class GPUCollector(BaseCollector):
    """Collects data for every GPU on the system (integrated + discrete,
    Intel/AMD/NVIDIA). Returns {"gpus": [...]} with one entry per adapter.

    The provider is built lazily, per thread: the WMI/COM objects it holds
    are apartment-bound, so one created on the main thread and then used
    from the collector thread fails with RPC_E_WRONG_THREAD. Binding it to
    the calling thread keeps it valid wherever collect() runs.
    """

    def __init__(self):
        self._local = threading.local()
        self.last_time = 0
        self.cached_gpus = []

    def _get_provider(self):
        provider = getattr(self._local, "provider", None)
        if provider is None:
            provider = get_multi_gpu_provider()
            self._local.provider = provider
        return provider

    def collect(self) -> Dict[str, Any]:
        now = time.monotonic()
        if now - self.last_time >= 5:
            self.cached_gpus = self._get_provider().get_all_data()
            self.last_time = now

        return {"gpus": self.cached_gpus}
