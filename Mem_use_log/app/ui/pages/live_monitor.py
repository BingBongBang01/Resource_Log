import customtkinter as ctk
from ui.pages.base_page import BasePage
from ui.theme import Colors, Spacing, get_typography
from ui.state_manager import app_state
from i18n import t
from config.settings import config

class StatRow(ctk.CTkFrame):
    """A label+value row, optionally with a checkbox that toggles whether
    this specific item gets written to the log (display always keeps
    updating regardless of the checkbox state)."""
    def __init__(self, master, label: str, value: str = "-", field_key: str = None, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.field_key = field_key
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_columnconfigure(2, weight=1)

        col = 0
        if field_key is not None:
            self.log_var = ctk.BooleanVar(value=config.LOG_FIELDS.get(field_key, True))
            self.chk_log = ctk.CTkCheckBox(self, text="", variable=self.log_var, width=20,
                                            command=self._on_toggle)
            self.chk_log.grid(row=0, column=0, sticky="w", padx=(0, Spacing.XS))
            col = 1

        self.lbl_label = ctk.CTkLabel(self, text=label, font=get_typography().body_medium, text_color=Colors.TEXT_SECONDARY)
        self.lbl_label.grid(row=0, column=col, sticky="w", pady=2)

        self.lbl_value = ctk.CTkLabel(self, text=value, font=get_typography().body_large, text_color=Colors.TEXT_PRIMARY)
        self.lbl_value.grid(row=0, column=col + 1, sticky="e", pady=2)

    def _on_toggle(self):
        config.LOG_FIELDS[self.field_key] = self.log_var.get()
        config.save()

    def set_value(self, value: str):
        self.lbl_value.configure(text=value)

class LiveMonitorPage(BasePage):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)

        self.grid_columnconfigure((0,1), weight=1)
        self.grid_rowconfigure(0, weight=1)

        # CPU & RAM Column
        col1 = ctk.CTkFrame(self, fg_color="transparent")
        col1.grid(row=0, column=0, sticky="nsew", padx=Spacing.MD, pady=Spacing.MD)

        # CPU Section
        lbl_cpu = ctk.CTkLabel(col1, text=t("cpu"), font=get_typography().title, text_color=Colors.PRIMARY)
        lbl_cpu.pack(anchor="w", pady=(0, Spacing.SM))

        self.cpu_usage = StatRow(col1, t("usage"), field_key="cpu_usage")
        self.cpu_usage.pack(fill="x")
        self.cpu_freq = StatRow(col1, t("frequency"), field_key="cpu_freq_mhz")
        self.cpu_freq.pack(fill="x")
        self.cpu_temp = StatRow(col1, t("temperature"), field_key="cpu_temperature")
        self.cpu_temp.pack(fill="x")

        # RAM Section
        lbl_ram = ctk.CTkLabel(col1, text=t("ram"), font=get_typography().title, text_color=Colors.PRIMARY)
        lbl_ram.pack(anchor="w", pady=(Spacing.LG, Spacing.SM))

        self.ram_used = StatRow(col1, t("used"), field_key="ram_used")
        self.ram_used.pack(fill="x")
        self.ram_avail = StatRow(col1, t("available"), field_key="ram_available")
        self.ram_avail.pack(fill="x")
        self.ram_total = StatRow(col1, t("total"), field_key="ram_total")
        self.ram_total.pack(fill="x")
        self.ram_util = StatRow(col1, t("usage"), field_key="ram_usage_percent")
        self.ram_util.pack(fill="x")

        # GPU Column
        col2 = ctk.CTkFrame(self, fg_color="transparent")
        col2.grid(row=0, column=1, sticky="nsew", padx=Spacing.MD, pady=Spacing.MD)

        lbl_gpu = ctk.CTkLabel(col2, text=t("gpu"), font=get_typography().title, text_color=Colors.PRIMARY)
        lbl_gpu.pack(anchor="w", pady=(0, Spacing.SM))

        # Metric-level checkboxes: these gate logging for every detected GPU
        # (Intel/AMD/Nvidia, integrated or discrete) at once, since the
        # number of GPUs isn't known ahead of time.
        self.gpu_usage = StatRow(col2, t("usage"), field_key="gpu_usage")
        self.gpu_usage.pack(fill="x")
        self.gpu_vram = StatRow(col2, t("vram"), field_key="gpu_vram_used")
        self.gpu_vram.pack(fill="x")
        self.gpu_temp = StatRow(col2, t("temperature"), field_key="gpu_temperature")
        self.gpu_temp.pack(fill="x")

        # Dynamic per-GPU readout: as many rows as GPUs are actually
        # detected (GPU 1, GPU 2, ...), rebuilt whenever the count changes.
        self.gpu_detail_frame = ctk.CTkFrame(col2, fg_color="transparent")
        self.gpu_detail_frame.pack(fill="x", pady=(Spacing.SM, 0))
        self.gpu_detail_rows = []

        self._bind_state()

    def _bind_state(self):
        app_state.add_listener("cpu_usage", lambda v: self.cpu_usage.set_value(f"{v}%"))
        # cpu_freq is carried in MHz; display it as GHz.
        app_state.add_listener("cpu_freq", lambda v: self.cpu_freq.set_value(f"{(v or 0) / 1000.0:.2f} GHz"))
        # Temperature needs a sensor backend (e.g. LibreHardwareMonitor);
        # without one it stays None and must not render as "None °C".
        app_state.add_listener("cpu_temp", lambda v: self.cpu_temp.set_value(
            f"{v} °C" if v is not None else t("unavailable")))

        app_state.add_listener("ram_used", lambda v: self.ram_used.set_value(f"{v} GB"))
        app_state.add_listener("ram_available", lambda v: self.ram_avail.set_value(f"{v} GB"))
        app_state.add_listener("ram_total", lambda v: self.ram_total.set_value(f"{v} GB"))
        app_state.add_listener("ram_percent", lambda v: self.ram_util.set_value(f"{v}%"))

        app_state.add_listener("gpu_data", self._update_gpu)

    def _update_gpu(self, gpu_list):
        if not gpu_list:
            self.gpu_usage.set_value("-")
            self.gpu_vram.set_value("-")
            self.gpu_temp.set_value(t("unavailable"))
            self._render_gpu_details([])
            return

        # Summary rows show the first/primary GPU's readings.
        primary = gpu_list[0]
        self.gpu_usage.set_value(f"{primary.get('gpu_usage', 0) or 0}%")
        self.gpu_vram.set_value(f"{primary.get('gpu_vram_used', 0) or 0} / {primary.get('gpu_vram_total', 0) or 0} GB")
        temp = primary.get('gpu_temperature')
        self.gpu_temp.set_value(f"{temp} °C" if temp is not None else t("unavailable"))

        self._render_gpu_details(gpu_list)

    def _render_gpu_details(self, gpu_list):
        # Rebuild dynamic rows if the GPU count changed (e.g. eGPU plugged in).
        if len(self.gpu_detail_rows) != len(gpu_list):
            for row in self.gpu_detail_rows:
                row.destroy()
            self.gpu_detail_rows = []
            for i, gpu in enumerate(gpu_list):
                label = t("gpu_detected", i + 1, gpu.get("name", "Unknown"))
                row = ctk.CTkLabel(self.gpu_detail_frame, text=label, font=get_typography().body_medium,
                                    text_color=Colors.TEXT_SECONDARY, anchor="w", justify="left")
                row.pack(fill="x", pady=1)
                self.gpu_detail_rows.append(row)

        for idx, (row, gpu) in enumerate(zip(self.gpu_detail_rows, gpu_list)):
            usage = gpu.get("gpu_usage")
            vram_used = gpu.get("gpu_vram_used")
            vram_total = gpu.get("gpu_vram_total")
            usage_str = f"{usage}%" if usage is not None else "-"
            if vram_used is None and vram_total is None:
                vram_str = "-"
            else:
                vram_str = f"{vram_used if vram_used is not None else 0}/{vram_total if vram_total is not None else 0} GB"
            label = t("gpu_detected", idx + 1, gpu.get("name", "Unknown"))
            row.configure(text=f"{label} — {usage_str}, {vram_str}")
