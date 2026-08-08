from typing import Any, Dict, List, Callable
from collections import defaultdict
import threading

class AppState:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(AppState, cls).__new__(cls)
                cls._instance._init_state()
            return cls._instance

    def _init_state(self):
        # Listeners map: key -> list of callbacks
        self._listeners: Dict[str, List[Callable]] = defaultdict(list)

        # When the window is minimised or hidden to the tray there is nothing
        # to repaint, so listeners are muted and the collectors skip pushing
        # UI updates entirely. Logging to disk continues either way.
        self.ui_active = True

        # Core State Dictionary
        self._state: Dict[str, Any] = {
            # Recording Status
            "recording_state": "stopped", # "stopped", "recording", "warning", "error"
            "recording_duration_sec": 0,

            # Health
            "collector_health": "Healthy",
            "database_health": "Healthy",
            "writer_health": "Healthy",
            "queue_size": 0,
            "last_collection": "N/A",
            "last_write": "N/A",
            "last_error": None,
            
            # Live Data (Latest metrics)
            "cpu_usage": 0.0,
            "cpu_freq": 0.0,
            "cpu_temp": 0.0,
            
            "ram_total": 0.0,
            "ram_used": 0.0,
            "ram_available": 0.0,
            "ram_percent": 0.0,
            "commit_limit": 0.0,
            "commit_used": 0.0,
            "commit_percent": 0.0,
            "pagefile_used": 0.0,
            
            "gpu_data": [],       # List of GPU dicts
            "storage_data": [],   # List of disk dicts
            "network_data": [],   # List of network dicts
            "process_data": []    # List of process dicts
        }

    def add_listener(self, key: str, callback: Callable):
        """Register a callback when a specific state key changes."""
        self._listeners[key].append(callback)

    def get(self, key: str, default: Any = None) -> Any:
        return self._state.get(key, default)

    def set(self, key: str, value: Any):
        """Update state and notify listeners if changed."""
        if self._state.get(key) != value:
            self._state[key] = value
            self._notify(key, value)
            
    def update(self, kwargs: Dict[str, Any]):
        """Update multiple keys at once."""
        changed = []
        for k, v in kwargs.items():
            if self._state.get(k) != v:
                self._state[k] = v
                changed.append((k, v))
                
        for k, v in changed:
            self._notify(k, v)

    def set_ui_active(self, active: bool):
        """Mute or resume UI listeners. Resuming replays current values once
        so the widgets catch up on whatever changed while hidden."""
        if active == self.ui_active:
            return
        self.ui_active = active
        if active:
            for key in list(self._listeners):
                if key in self._state:
                    self._notify(key, self._state[key])

    def _notify(self, key: str, value: Any):
        if not self.ui_active:
            return
        for callback in self._listeners[key]:
            try:
                callback(value)
            except Exception as e:
                from utils.logger import logger
                logger.error(f"UI State listener error on key {key}: {e}")

# Global instance
app_state = AppState()
