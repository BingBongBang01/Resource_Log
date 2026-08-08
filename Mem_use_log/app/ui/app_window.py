import time
import customtkinter as ctk
from ui.theme import Colors, Spacing, get_typography
from ui.components.navigation import NavigationRail
from ui.state_manager import app_state
from i18n import t
from config.settings import config

from ui.pages.base_page import BasePage
from ui.pages.dashboard import DashboardPage
from ui.pages.live_monitor import LiveMonitorPage
from ui.pages.overlay import OverlayPage
from ui.pages.export import ExportPage
from ui.overlay_window import OverlayWindow
from providers.fps_provider import get_fps_provider
from ui.pages.settings import SettingsPage
from ui.pages.diagnostics import DiagnosticsPage

class TopAppBar(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color="transparent", height=60, **kwargs)
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=0)
        
        # Title
        self.title_label = ctk.CTkLabel(self, text=t("nav_dashboard"), font=get_typography().headline, text_color=Colors.TEXT_PRIMARY)
        self.title_label.grid(row=0, column=0, sticky="w", padx=Spacing.MD, pady=Spacing.MD)

        # Recording Status Widget
        self.status_frame = ctk.CTkFrame(self, fg_color=Colors.SURFACE_CONTAINER_HIGH, corner_radius=16)
        self.status_frame.grid(row=0, column=1, sticky="e", padx=Spacing.MD, pady=Spacing.MD)

        self.status_indicator = ctk.CTkLabel(self.status_frame, text=t("status_not_recording"), font=get_typography().body_medium, text_color=Colors.TEXT_SECONDARY)
        self.status_indicator.pack(padx=Spacing.MD, pady=Spacing.XS)

        app_state.add_listener("recording_state", self._on_state_change)

    def set_title(self, title: str):
        self.title_label.configure(text=title)

    def _on_state_change(self, state: str):
        if state == "recording":
            self.status_indicator.configure(text=t("status_recording"), text_color=Colors.ERROR)
        elif state == "warning":
            self.status_indicator.configure(text=t("status_warning"), text_color=Colors.WARNING)
        else:
            self.status_indicator.configure(text=t("status_not_recording"), text_color=Colors.TEXT_SECONDARY)

class AppWindow(ctk.CTk):
    def __init__(self, collector_loop):
        super().__init__()
        self.collector = collector_loop
        
        self.title(t("app_title"))
        self.geometry("1024x768")
        self.minsize(800, 600)

        ctk.set_appearance_mode("Dark")
        self.configure(fg_color=Colors.SURFACE)

        # Main layout: NavRail left, Content right
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)

        # Nav Rail
        self.nav_rail = NavigationRail(self, on_navigate=self._on_navigate)
        self.nav_rail.grid(row=0, column=0, sticky="nsew")

        destinations = [
            ("Dashboard", t("nav_dashboard")),
            ("Live Monitor", t("nav_live_monitor")),
            ("Overlay", t("nav_overlay")),
            ("Export", t("nav_export")),
            ("Diagnostics", t("nav_diagnostics")),
        ]
        for key, label in destinations:
            self.nav_rail.add_destination(key, display_name=label)
            
        # Right Content Area
        self.content_area = ctk.CTkFrame(self, fg_color="transparent")
        self.content_area.grid(row=0, column=1, sticky="nsew")
        self.content_area.grid_rowconfigure(0, weight=0) # Top Bar
        self.content_area.grid_rowconfigure(1, weight=1) # Page Content
        self.content_area.grid_columnconfigure(0, weight=1)
        
        self.top_bar = TopAppBar(self.content_area)
        self.top_bar.grid(row=0, column=0, sticky="ew")
        
        self.page_container = ctk.CTkFrame(self.content_area, fg_color="transparent")
        self.page_container.grid(row=1, column=0, sticky="nsew", padx=Spacing.MD, pady=(0, Spacing.MD))
        self.page_container.grid_rowconfigure(0, weight=1)
        self.page_container.grid_columnconfigure(0, weight=1)
        
        # Initialize Pages
        self.pages = {
            "Dashboard": DashboardPage(self.page_container),
            "Live Monitor": LiveMonitorPage(self.page_container),
            "Overlay": OverlayPage(self.page_container),
            "Export": ExportPage(self.page_container, self.collector.db),
            "Diagnostics": DiagnosticsPage(self.page_container),
            "Settings": SettingsPage(self.page_container)
        }
        
        # Connect recording control logic for the dashboard
        self.pages["Dashboard"].rec_control.btn_toggle.configure(command=self.toggle_recording)

        self.nav_titles = dict(destinations)
        self.nav_titles["Settings"] = t("nav_settings")

        # On-screen overlay: its own window and refresh loop, independent of
        # which page is open or whether the main window is even visible.
        self.overlay = OverlayWindow(self)
        self.fps_provider = get_fps_provider()
        self.pages["Overlay"].on_overlay_changed = self._on_overlay_settings_changed
        self.after(1000, self._refresh_overlay)

        # Start a loop to pull state from backend to app_state
        self.recording_started_at = None
        self.bind("<Unmap>", self._on_visibility_change)
        self.bind("<Map>", self._on_visibility_change)
        self.after(1000, self._sync_backend_state)

        self.current_page = None
        self.nav_rail.select("Dashboard")

        # Closing the window is just one of several ways this process can
        # end; they all converge on utils.shutdown so the logs get saved
        # exactly once regardless of which one fires.
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Auto-start logging on launch if enabled in settings
        if config.AUTO_START_RECORDING and not self.collector.running:
            self.toggle_recording()

    def _on_close(self):
        from utils import shutdown
        shutdown.run_now("window closed")
        self.destroy()

    def toggle_recording(self):
        if not self.collector.running:
            self.collector.start()
            self.recording_started_at = time.monotonic()
            app_state.update({"recording_state": "recording", "recording_duration_sec": 0})
        else:
            # save_and_stop rather than stop: one finished run, one CSV,
            # whether the run ends here or because the PC is shutting down.
            self.collector.save_and_stop()
            self.recording_started_at = None
            app_state.set("recording_state", "stopped")

    def _on_overlay_settings_changed(self):
        self.overlay.set_opacity(config.OVERLAY_OPACITY)
        if not config.OVERLAY_ENABLED:
            self.overlay.hide()
        else:
            self._refresh_overlay(reschedule=False)

    @staticmethod
    def _fmt(value, suffix="", decimals=1):
        if value is None:
            return None
        try:
            return f"{float(value):.{decimals}f}{suffix}"
        except (TypeError, ValueError):
            return None

    def _build_overlay_values(self, game):
        """Format the current metrics into overlay-ready strings. Anything
        unavailable stays None and its row is simply not drawn."""
        gpus = app_state.get("gpu_data") or []
        gpu = gpus[0] if gpus else {}

        values = {
            "cpu_usage": self._fmt(app_state.get("cpu_usage"), "%", 0),
            "cpu_temp": self._fmt(app_state.get("cpu_temp"), "°C", 0),
            "ram_used": self._fmt(app_state.get("ram_used"), " GB", 1),
            "ram_percent": self._fmt(app_state.get("ram_percent"), "%", 0),
            "gpu_usage": self._fmt(gpu.get("gpu_usage"), "%", 0),
            "gpu_temp": self._fmt(gpu.get("gpu_temperature"), "°C", 0),
        }
        values = {k: (f"{t(f'overlay_{k}')}  {v}" if v else None) for k, v in values.items()}

        vram_used, vram_total = gpu.get("gpu_vram_used"), gpu.get("gpu_vram_total")
        if vram_used is not None:
            total = f" / {vram_total:.1f}" if vram_total else ""
            values["gpu_vram"] = f"{t('overlay_gpu_vram')}  {vram_used:.1f}{total} GB"
        else:
            values["gpu_vram"] = None

        if game:
            for key, src, suffix, dec in (
                ("fps", "fps", "", 0),
                ("fps_avg", "fps_avg", "", 1),
                ("fps_min", "fps_min", "", 0),
                ("fps_max", "fps_max", "", 0),
                ("frame_time", "frame_time_ms", " ms", 2),
            ):
                formatted = self._fmt(game.get(src), suffix, dec)
                values[key] = f"{t(f'overlay_{key}')}  {formatted}" if formatted else None

        return values

    def _refresh_overlay(self, reschedule=True):
        try:
            if config.OVERLAY_ENABLED:
                # RTSS reporting frames for a process is our definition of
                # "a game is running" — it's the same signal that supplies
                # the numbers, so the two can never disagree.
                game = self.fps_provider.get_active_app()
                self.overlay.render(self._build_overlay_values(game), game_active=game is not None)
            else:
                self.overlay.hide()
        except Exception:
            from utils.logger import logger
            logger.exception("Overlay refresh failed")
        finally:
            if reschedule:
                self.after(1000, self._refresh_overlay)

    def _on_visibility_change(self, event=None):
        """Minimising to the taskbar/tray mutes all UI refresh work; logging
        to disk keeps running untouched."""
        try:
            visible = self.state() not in ("iconic", "withdrawn")
        except Exception:
            visible = True
        app_state.set_ui_active(visible)

    def _sync_backend_state(self):
        # Nothing on screen to refresh while hidden — poll far less often.
        if not app_state.ui_active:
            self.after(5000, self._sync_backend_state)
            return

        if self.collector and self.collector.writer:
            q_size = self.collector.writer.get_queue_size()
            last_w = self.collector.writer.get_last_write_time() or "N/A"
            app_state.update({"queue_size": q_size, "last_write": last_w})

        if self.recording_started_at is not None and self.collector.running:
            elapsed = int(time.monotonic() - self.recording_started_at)
            app_state.set("recording_duration_sec", elapsed)

        self.after(1000, self._sync_backend_state)
        
    def _on_navigate(self, page_name: str):
        if self.current_page:
            self.pages[self.current_page].grid_forget()
            self.pages[self.current_page].on_hide()
            
        self.current_page = page_name
        self.top_bar.set_title(self.nav_titles.get(page_name, page_name))
        
        page = self.pages[page_name]
        page.grid(row=0, column=0, sticky="nsew")
        page.on_show()
