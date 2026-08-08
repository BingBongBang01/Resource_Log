import os
import sys
import json
from utils.logger import logger


def _resolve_project_root() -> str:
    """Directory that holds config.json, data/ and logs/.

    When frozen with PyInstaller, __file__ points inside the bundle — for
    a onefile build that's a temp folder wiped on exit, which would silently
    throw away the database and settings. Anchor to the executable instead.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))


PROJECT_ROOT = _resolve_project_root()

DEFAULT_LOG_FIELDS = {
    "cpu_usage": True,
    "cpu_freq_mhz": True,
    "cpu_temperature": True,
    "ram_used": True,
    "ram_available": True,
    "ram_total": True,
    "ram_usage_percent": True,
    "gpu_usage": True,
    "gpu_vram_used": True,
    "gpu_temperature": True,
}

# Which collector each loggable field belongs to. A collector whose fields
# are all unchecked is skipped entirely rather than collected and discarded —
# that's what makes unchecking GPU actually save CPU (its WMI query is by far
# the most expensive thing this app does).
FIELD_GROUPS = {
    "cpu": ("cpu_usage", "cpu_freq_mhz", "cpu_temperature"),
    "memory": ("ram_used", "ram_available", "ram_total", "ram_usage_percent"),
    "gpu": ("gpu_usage", "gpu_vram_used", "gpu_temperature"),
}

# What the on-screen overlay can show, in display order. The fps_* rows only
# appear while a game is actually being measured.
OVERLAY_ITEM_ORDER = (
    "cpu_usage", "cpu_temp",
    "ram_used", "ram_percent",
    "gpu_usage", "gpu_vram", "gpu_temp",
    "fps", "fps_avg", "fps_min", "fps_max", "frame_time",
)

DEFAULT_OVERLAY_ITEMS = {
    "cpu_usage": True,
    "cpu_temp": False,
    "ram_used": True,
    "ram_percent": False,
    "gpu_usage": True,
    "gpu_vram": False,
    "gpu_temp": False,
    "fps": True,
    "fps_avg": True,
    "fps_min": False,
    "fps_max": False,
    "frame_time": False,
}

OVERLAY_POSITIONS = ("top_left", "top_right", "bottom_left", "bottom_right")


class Settings:
    def __init__(self):
        self.SYSTEM_COLLECTION_INTERVAL_MS = 5000
        self.PROCESS_COLLECTION_INTERVAL = 60
        # GPU sensing costs ~350ms per sample (Windows' GPU perf counters are
        # slow), so it runs on its own thread with its own, slower cadence
        # instead of stalling the CPU/RAM sampling loop.
        self.GPU_COLLECTION_INTERVAL_MS = 10000
        self.AUTO_START_RECORDING = True
        self.EXPORT_DIRECTORY = os.path.join(PROJECT_ROOT, "data", "exports")
        self.LANGUAGE = "ko"
        self.START_ON_BOOT = False
        # Per-item toggle for what the live monitor actually logs to disk.
        self.LOG_FIELDS = dict(DEFAULT_LOG_FIELDS)

        # On-screen overlay
        self.OVERLAY_ENABLED = False
        self.OVERLAY_POSITION = "top_left"
        self.OVERLAY_ITEMS = dict(DEFAULT_OVERLAY_ITEMS)
        self.OVERLAY_OPACITY = 0.80
        self.OVERLAY_MARGIN = 12

    def group_enabled(self, group: str) -> bool:
        """True if any field of this collector is still being logged."""
        return any(self.LOG_FIELDS.get(f, True) for f in FIELD_GROUPS.get(group, ()))

    def load(self, path: str = "config.json"):
        full_path = os.path.join(PROJECT_ROOT, path)
        if os.path.exists(full_path):
            try:
                with open(full_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    
                    sys_interval = data.get("system_collection_interval_ms", self.SYSTEM_COLLECTION_INTERVAL_MS)
                    if isinstance(sys_interval, int) and sys_interval > 0:
                        self.SYSTEM_COLLECTION_INTERVAL_MS = sys_interval
                        
                    proc_interval = data.get("process_collection_interval", self.PROCESS_COLLECTION_INTERVAL)
                    if isinstance(proc_interval, int) and proc_interval > 0:
                        self.PROCESS_COLLECTION_INTERVAL = proc_interval

                    gpu_interval = data.get("gpu_collection_interval_ms", self.GPU_COLLECTION_INTERVAL_MS)
                    if isinstance(gpu_interval, int) and gpu_interval > 0:
                        self.GPU_COLLECTION_INTERVAL_MS = gpu_interval


                    self.AUTO_START_RECORDING = data.get("auto_start_recording", self.AUTO_START_RECORDING)
                    
                    export_dir = data.get("export_directory")
                    if export_dir and isinstance(export_dir, str):
                        self.EXPORT_DIRECTORY = export_dir

                    language = data.get("language")
                    if language in ("en", "ko"):
                        self.LANGUAGE = language

                    self.START_ON_BOOT = bool(data.get("start_on_boot", self.START_ON_BOOT))

                    log_fields = data.get("log_fields")
                    if isinstance(log_fields, dict):
                        for key in self.LOG_FIELDS:
                            if key in log_fields:
                                self.LOG_FIELDS[key] = bool(log_fields[key])

                    self.OVERLAY_ENABLED = bool(data.get("overlay_enabled", self.OVERLAY_ENABLED))

                    position = data.get("overlay_position")
                    if position in OVERLAY_POSITIONS:
                        self.OVERLAY_POSITION = position

                    overlay_items = data.get("overlay_items")
                    if isinstance(overlay_items, dict):
                        for key in self.OVERLAY_ITEMS:
                            if key in overlay_items:
                                self.OVERLAY_ITEMS[key] = bool(overlay_items[key])

                    opacity = data.get("overlay_opacity")
                    if isinstance(opacity, (int, float)) and 0.1 <= opacity <= 1.0:
                        self.OVERLAY_OPACITY = float(opacity)
            except Exception as e:
                logger.error(f"Failed to load config: {e}")

        try:
            from i18n import set_language
            set_language(self.LANGUAGE)
        except Exception as e:
            logger.error(f"Failed to apply language setting: {e}")
                
    def save(self, path: str = "config.json"):
        full_path = os.path.join(PROJECT_ROOT, path)
        data = {
            "system_collection_interval_ms": self.SYSTEM_COLLECTION_INTERVAL_MS,
            "process_collection_interval": self.PROCESS_COLLECTION_INTERVAL,
            "gpu_collection_interval_ms": self.GPU_COLLECTION_INTERVAL_MS,
            "auto_start_recording": self.AUTO_START_RECORDING,
            "export_directory": self.EXPORT_DIRECTORY,
            "language": self.LANGUAGE,
            "start_on_boot": self.START_ON_BOOT,
            "log_fields": self.LOG_FIELDS,
            "overlay_enabled": self.OVERLAY_ENABLED,
            "overlay_position": self.OVERLAY_POSITION,
            "overlay_items": self.OVERLAY_ITEMS,
            "overlay_opacity": self.OVERLAY_OPACITY,
        }
        try:
            with open(full_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            logger.error(f"Failed to save config: {e}")

config = Settings()
config.load()
