import os
import json
from utils.logger import logger

# Re-exported: storage.database and others import PROJECT_ROOT from here.
from utils.paths import PROJECT_ROOT

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
    # Frame rate, recorded per game the same way the overlay shows it.
    "fps": True,
    "fps_avg": True,
    "fps_min": True,
    "fps_max": True,
    "frame_time": True,
}

# Which collector each loggable field belongs to. A collector whose fields
# are all unchecked is skipped entirely rather than collected and discarded —
# that's what makes unchecking GPU actually save CPU (its WMI query is by far
# the most expensive thing this app does).
FIELD_GROUPS = {
    "cpu": ("cpu_usage", "cpu_freq_mhz", "cpu_temperature"),
    "memory": ("ram_used", "ram_available", "ram_total", "ram_usage_percent"),
    "gpu": ("gpu_usage", "gpu_vram_used", "gpu_temperature"),
    "fps": ("fps", "fps_avg", "fps_min", "fps_max", "frame_time"),
}

# The loggable FPS fields, in the order the exporter writes them.
FPS_LOG_FIELDS = FIELD_GROUPS["fps"]

# What the on-screen overlay can show, in display order. The fps_* rows only
# appear while a game is actually being measured.
OVERLAY_ITEM_ORDER = (
    "cpu_usage", "cpu_temp",
    "ram_used", "ram_percent",
    "gpu_usage", "gpu_vram", "gpu_temp",
    "fps", "fps_avg", "fps_min", "fps_max", "frame_time",
)

# Frame rate only, like the GeForce Experience counter this is modelled on.
# Everything else is opt-in from the Overlay page.
DEFAULT_OVERLAY_ITEMS = {
    "cpu_usage": False,
    "cpu_temp": False,
    "ram_used": False,
    "ram_percent": False,
    "gpu_usage": False,
    "gpu_vram": False,
    "gpu_temp": False,
    "fps": True,
    "fps_avg": False,
    "fps_min": False,
    "fps_max": False,
    "frame_time": False,
}

OVERLAY_POSITIONS = ("top_left", "top_right", "bottom_left", "bottom_right")


def _is_hex_color(value: str) -> bool:
    return (
        len(value) == 7
        and value.startswith("#")
        and all(c in "0123456789abcdefABCDEF" for c in value[1:])
    )


def hex_to_rgb(value: str, fallback=(255, 255, 255)):
    """'#39FF14' -> (57, 255, 20). Never raises: a bad colour in config.json
    must not stop the overlay from drawing."""
    if not isinstance(value, str) or not _is_hex_color(value):
        return fallback
    return tuple(int(value[i:i + 2], 16) for i in (1, 3, 5))


class Settings:
    def __init__(self):
        self.SYSTEM_COLLECTION_INTERVAL_MS = 5000
        self.PROCESS_COLLECTION_INTERVAL = 60
        # GPU sensing costs ~350ms per sample (Windows' GPU perf counters are
        # slow), so it runs on its own thread with its own, slower cadence
        # instead of stalling the CPU/RAM sampling loop.
        self.GPU_COLLECTION_INTERVAL_MS = 10000
        self.AUTO_START_RECORDING = True
        # Write the finished run out as CSV whenever logging stops — including
        # when Windows shuts down underneath us.
        self.AUTO_EXPORT_ON_EXIT = True
        self.EXPORT_DIRECTORY = os.path.join(PROJECT_ROOT, "data", "exports")
        self.LANGUAGE = "ko"
        self.START_ON_BOOT = False
        # Per-item toggle for what the live monitor actually logs to disk.
        self.LOG_FIELDS = dict(DEFAULT_LOG_FIELDS)

        # On-screen overlay. Text and background carry their own opacity —
        # the default is an unboxed counter, green digits on nothing at all.
        self.OVERLAY_ENABLED = False
        self.OVERLAY_POSITION = "top_left"
        self.OVERLAY_ITEMS = dict(DEFAULT_OVERLAY_ITEMS)
        self.OVERLAY_TEXT_OPACITY = 1.00
        self.OVERLAY_BG_OPACITY = 0.00
        self.OVERLAY_FONT_SIZE = 34
        self.OVERLAY_TEXT_COLOR = "#39FF14"
        self.OVERLAY_BG_COLOR = "#000000"
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
                    self.AUTO_EXPORT_ON_EXIT = bool(data.get("auto_export_on_exit", self.AUTO_EXPORT_ON_EXIT))

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

                    # overlay_opacity was one value for the whole window before
                    # text and background could differ; carry it over as the
                    # text opacity so an existing config doesn't go invisible.
                    legacy_opacity = data.get("overlay_opacity")
                    if isinstance(legacy_opacity, (int, float)) and 0.0 <= legacy_opacity <= 1.0:
                        self.OVERLAY_TEXT_OPACITY = float(legacy_opacity)

                    for key, attr in (
                        ("overlay_text_opacity", "OVERLAY_TEXT_OPACITY"),
                        ("overlay_bg_opacity", "OVERLAY_BG_OPACITY"),
                    ):
                        value = data.get(key)
                        if isinstance(value, (int, float)) and 0.0 <= value <= 1.0:
                            setattr(self, attr, float(value))

                    font_size = data.get("overlay_font_size")
                    if isinstance(font_size, int) and 8 <= font_size <= 200:
                        self.OVERLAY_FONT_SIZE = font_size

                    for key, attr in (
                        ("overlay_text_color", "OVERLAY_TEXT_COLOR"),
                        ("overlay_bg_color", "OVERLAY_BG_COLOR"),
                    ):
                        value = data.get(key)
                        if isinstance(value, str) and _is_hex_color(value):
                            setattr(self, attr, value)
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
            "auto_export_on_exit": self.AUTO_EXPORT_ON_EXIT,
            "export_directory": self.EXPORT_DIRECTORY,
            "language": self.LANGUAGE,
            "start_on_boot": self.START_ON_BOOT,
            "log_fields": self.LOG_FIELDS,
            "overlay_enabled": self.OVERLAY_ENABLED,
            "overlay_position": self.OVERLAY_POSITION,
            "overlay_items": self.OVERLAY_ITEMS,
            "overlay_text_opacity": self.OVERLAY_TEXT_OPACITY,
            "overlay_bg_opacity": self.OVERLAY_BG_OPACITY,
            "overlay_font_size": self.OVERLAY_FONT_SIZE,
            "overlay_text_color": self.OVERLAY_TEXT_COLOR,
            "overlay_bg_color": self.OVERLAY_BG_COLOR,
        }
        try:
            with open(full_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            logger.error(f"Failed to save config: {e}")

config = Settings()
config.load()
