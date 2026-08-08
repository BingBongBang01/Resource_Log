import customtkinter as ctk
from ui.pages.base_page import BasePage
from ui.components.cards import ResourceCard, MetricCard
from ui.theme import Colors, Spacing, get_typography
from ui.state_manager import app_state
from i18n import t
from datetime import timedelta

class RecordingControl(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color=Colors.SURFACE_CONTAINER_HIGH, corner_radius=12, **kwargs)

        self.grid_columnconfigure(0, weight=1)

        self.lbl_status = ctk.CTkLabel(self, text=t("status_not_recording"), font=get_typography().title, text_color=Colors.TEXT_SECONDARY)
        self.lbl_status.grid(row=0, column=0, sticky="w", padx=Spacing.MD, pady=(Spacing.MD, Spacing.XS))

        self.lbl_duration = ctk.CTkLabel(self, text=t("duration_label", "00:00:00"), font=get_typography().body_medium, text_color=Colors.TEXT_SECONDARY)
        self.lbl_duration.grid(row=1, column=0, sticky="w", padx=Spacing.MD, pady=(0, Spacing.MD))

        self.btn_toggle = ctk.CTkButton(self, text=t("start_recording"), font=get_typography().body_large,
                                        fg_color=Colors.PRIMARY, text_color=Colors.ON_PRIMARY,
                                        command=self._on_toggle)
        self.btn_toggle.grid(row=3, column=0, sticky="ew", padx=Spacing.MD, pady=(0, Spacing.MD))

        app_state.add_listener("recording_state", self._on_state_change)
        app_state.add_listener("recording_duration_sec", self._on_duration_change)

    def _on_state_change(self, state: str):
        if state == "recording":
            self.lbl_status.configure(text=t("status_recording"), text_color=Colors.ERROR)
            self.btn_toggle.configure(text=t("stop_recording"), fg_color=Colors.ERROR, text_color=Colors.SURFACE)
        else:
            self.lbl_status.configure(text=t("status_not_recording"), text_color=Colors.TEXT_SECONDARY)
            self.btn_toggle.configure(text=t("start_recording"), fg_color=Colors.PRIMARY, text_color=Colors.ON_PRIMARY)

    def _on_duration_change(self, secs: int):
        self.lbl_duration.configure(text=t("duration_label", timedelta(seconds=secs)))
        
    def _on_toggle(self):
        # The logic will be handled by the main app controller hooking into this later.
        # For now, we simulate sending a command to start/stop via a callback.
        # We'll attach this properly in Phase 10.
        pass

class DashboardPage(BasePage):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=2)
        
        # Left Column (Recording & Health)
        self.left_col = ctk.CTkFrame(self, fg_color="transparent")
        self.left_col.grid(row=0, column=0, sticky="nsew", padx=Spacing.MD, pady=Spacing.MD)
        self.left_col.grid_columnconfigure(0, weight=1)
        
        self.rec_control = RecordingControl(self.left_col)
        self.rec_control.grid(row=0, column=0, sticky="ew", pady=(0, Spacing.MD))
        
        # Right Column (System Overview)
        self.right_col = ctk.CTkFrame(self, fg_color="transparent")
        self.right_col.grid(row=0, column=1, sticky="nsew", padx=Spacing.MD, pady=Spacing.MD)
        self.right_col.grid_columnconfigure((0,1,2), weight=1)
        
        lbl_overview = ctk.CTkLabel(self.right_col, text=t("system_overview"), font=get_typography().title, text_color=Colors.TEXT_PRIMARY)
        lbl_overview.grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, Spacing.SM))

        self.cpu_card = ResourceCard(self.right_col, t("cpu"), "0%", "0.00 GHz")
        self.cpu_card.grid(row=1, column=0, sticky="ew", padx=Spacing.XS, pady=Spacing.XS)

        self.ram_card = ResourceCard(self.right_col, t("ram"), "0.0 / 0.0 GB", "0%", "P95: -")
        self.ram_card.grid(row=1, column=1, sticky="ew", padx=Spacing.XS, pady=Spacing.XS)

        self.gpu_card = ResourceCard(self.right_col, t("gpu"), "0%", "0.0 GB")
        self.gpu_card.grid(row=1, column=2, sticky="ew", padx=Spacing.XS, pady=Spacing.XS)
        
        # Setup listeners
        def update_cpu(_):
            usage = app_state.get('cpu_usage', 0)
            # cpu_freq is carried in MHz; the card shows GHz.
            freq_ghz = (app_state.get('cpu_freq', 0) or 0) / 1000.0
            self.cpu_card.update_data(f"{usage}%", f"{freq_ghz:.2f} GHz")

        app_state.add_listener("cpu_usage", update_cpu)
        app_state.add_listener("cpu_freq", update_cpu)

        def update_ram(_):
            used = app_state.get('ram_used', 0)
            total = app_state.get('ram_total', 0)
            pct = app_state.get('ram_percent', 0)
            self.ram_card.update_data(f"{used} / {total} GB", f"{pct}%")

        app_state.add_listener("ram_used", update_ram)
        app_state.add_listener("ram_total", update_ram)

        def update_gpu(gpu_list):
            # Card shows the primary GPU; the Live Monitor lists them all.
            if not gpu_list:
                self.gpu_card.update_data("-", "-", t("no_gpu_detected"))
                return
            gpu = gpu_list[0]
            usage = gpu.get("gpu_usage")
            used, total = gpu.get("gpu_vram_used"), gpu.get("gpu_vram_total")
            extra = t("gpu_count_more", len(gpu_list) - 1) if len(gpu_list) > 1 else gpu.get("name", "")
            self.gpu_card.update_data(
                f"{usage}%" if usage is not None else "-",
                f"{used if used is not None else 0} / {total if total is not None else 0} GB",
                extra,
            )

        app_state.add_listener("gpu_data", update_gpu)
