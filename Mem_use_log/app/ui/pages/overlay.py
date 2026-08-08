import customtkinter as ctk

from ui.pages.base_page import BasePage
from ui.theme import Colors, Spacing, get_typography
from config.settings import config, _is_hex_color
from i18n import t
from providers.fps_provider import get_fps_provider

# (config key, translation key) grouped as they appear in the tab.
RESOURCE_ITEMS = [
    ("cpu_usage", "overlay_cpu_usage"),
    ("cpu_temp", "overlay_cpu_temp"),
    ("ram_used", "overlay_ram_used"),
    ("ram_percent", "overlay_ram_percent"),
    ("gpu_usage", "overlay_gpu_usage"),
    ("gpu_vram", "overlay_gpu_vram"),
    ("gpu_temp", "overlay_gpu_temp"),
]

FPS_ITEMS = [
    ("fps", "overlay_fps"),
    ("fps_avg", "overlay_fps_avg"),
    ("fps_min", "overlay_fps_min"),
    ("fps_max", "overlay_fps_max"),
    ("frame_time", "overlay_frame_time"),
]

POSITION_KEYS = [
    ("top_left", "overlay_pos_top_left"),
    ("top_right", "overlay_pos_top_right"),
    ("bottom_left", "overlay_pos_bottom_left"),
    ("bottom_right", "overlay_pos_bottom_right"),
]


class OverlayPage(BasePage):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)

        self.grid_columnconfigure((0, 1), weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, columnspan=2, sticky="ew", padx=Spacing.MD, pady=(Spacing.MD, 0))

        self.enabled_var = ctk.BooleanVar(value=config.OVERLAY_ENABLED)
        self.chk_enabled = ctk.CTkSwitch(
            header, text=t("overlay_enable"), variable=self.enabled_var,
            font=get_typography().body_large, text_color=Colors.TEXT_PRIMARY,
            command=self._on_change,
        )
        self.chk_enabled.pack(anchor="w")

        # --- left column: which metrics ---
        left = ctk.CTkFrame(self, fg_color="transparent")
        left.grid(row=1, column=0, sticky="nsew", padx=Spacing.MD, pady=Spacing.MD)

        ctk.CTkLabel(left, text=t("overlay_items"), font=get_typography().title,
                     text_color=Colors.PRIMARY).pack(anchor="w", pady=(0, Spacing.SM))

        self.item_vars = {}
        for key, label_key in RESOURCE_ITEMS:
            var = ctk.BooleanVar(value=config.OVERLAY_ITEMS.get(key, False))
            self.item_vars[key] = var
            ctk.CTkCheckBox(left, text=t(label_key), variable=var, command=self._on_change,
                            font=get_typography().body_medium,
                            text_color=Colors.TEXT_PRIMARY).pack(anchor="w", pady=1)

        ctk.CTkLabel(left, text=t("overlay_fps_section"), font=get_typography().title,
                     text_color=Colors.PRIMARY).pack(anchor="w", pady=(Spacing.LG, Spacing.SM))

        for key, label_key in FPS_ITEMS:
            var = ctk.BooleanVar(value=config.OVERLAY_ITEMS.get(key, False))
            self.item_vars[key] = var
            ctk.CTkCheckBox(left, text=t(label_key), variable=var, command=self._on_change,
                            font=get_typography().body_medium,
                            text_color=Colors.TEXT_PRIMARY).pack(anchor="w", pady=1)

        self.lbl_fps_status = ctk.CTkLabel(
            left, text="", font=get_typography().label,
            text_color=Colors.TEXT_SECONDARY, wraplength=340, justify="left")
        self.lbl_fps_status.pack(anchor="w", pady=(Spacing.SM, 0))

        # --- right column: where on screen ---
        right = ctk.CTkFrame(self, fg_color="transparent")
        right.grid(row=1, column=1, sticky="nsew", padx=Spacing.MD, pady=Spacing.MD)

        ctk.CTkLabel(right, text=t("overlay_position"), font=get_typography().title,
                     text_color=Colors.PRIMARY).pack(anchor="w", pady=(0, Spacing.SM))

        # A 2x2 grid of radio buttons laid out like the screen corners they map to.
        grid = ctk.CTkFrame(right, fg_color=Colors.SURFACE_CONTAINER_HIGH, corner_radius=12)
        grid.pack(anchor="w", fill="x", pady=(0, Spacing.MD))
        grid.grid_columnconfigure((0, 1), weight=1)

        self.position_var = ctk.StringVar(value=config.OVERLAY_POSITION)
        cells = {"top_left": (0, 0), "top_right": (0, 1),
                 "bottom_left": (1, 0), "bottom_right": (1, 1)}
        for key, label_key in POSITION_KEYS:
            r, c = cells[key]
            ctk.CTkRadioButton(grid, text=t(label_key), value=key, variable=self.position_var,
                               command=self._on_change, font=get_typography().body_medium,
                               text_color=Colors.TEXT_PRIMARY).grid(
                row=r, column=c, sticky="w", padx=Spacing.MD, pady=Spacing.MD)

        # Text and background carry separate opacities: the default look is
        # bare digits over the game with no panel behind them at all.
        self.text_opacity_slider = self._add_slider(
            right, "overlay_text_opacity", config.OVERLAY_TEXT_OPACITY, self._on_text_opacity)
        self.bg_opacity_slider = self._add_slider(
            right, "overlay_bg_opacity", config.OVERLAY_BG_OPACITY, self._on_bg_opacity)

        ctk.CTkLabel(right, text=t("overlay_font_size"), font=get_typography().body_large,
                     text_color=Colors.TEXT_PRIMARY).pack(anchor="w", pady=(Spacing.SM, 0))
        self.font_size_slider = ctk.CTkSlider(right, from_=12, to=96, number_of_steps=84,
                                              command=self._on_font_size)
        self.font_size_slider.set(config.OVERLAY_FONT_SIZE)
        self.font_size_slider.pack(anchor="w", fill="x", pady=Spacing.XS)

        self.text_color_var = self._add_color_row(right, "overlay_text_color",
                                                  config.OVERLAY_TEXT_COLOR)
        self.bg_color_var = self._add_color_row(right, "overlay_bg_color",
                                                config.OVERLAY_BG_COLOR)

        ctk.CTkLabel(right, text=t("overlay_fullscreen_note"), font=get_typography().label,
                     text_color=Colors.TEXT_SECONDARY, wraplength=340,
                     justify="left").pack(anchor="w", pady=(Spacing.LG, 0))

        self.on_overlay_changed = None  # set by AppWindow

    @staticmethod
    def _add_slider(parent, label_key, value, command):
        ctk.CTkLabel(parent, text=t(label_key), font=get_typography().body_large,
                     text_color=Colors.TEXT_PRIMARY).pack(anchor="w", pady=(Spacing.SM, 0))
        slider = ctk.CTkSlider(parent, from_=0.0, to=1.0, number_of_steps=20, command=command)
        slider.set(value)
        slider.pack(anchor="w", fill="x", pady=Spacing.XS)
        return slider

    def _add_color_row(self, parent, label_key, value):
        """Colour as a typed hex code plus a live swatch — a full colour
        picker would be a lot of dialog for two settings."""
        ctk.CTkLabel(parent, text=t(label_key), font=get_typography().body_large,
                     text_color=Colors.TEXT_PRIMARY).pack(anchor="w", pady=(Spacing.SM, 0))

        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(anchor="w", fill="x", pady=Spacing.XS)

        var = ctk.StringVar(value=value)
        entry = ctk.CTkEntry(row, textvariable=var, width=110)
        entry.pack(side="left")

        swatch = ctk.CTkFrame(row, width=32, height=28, corner_radius=6, fg_color=value)
        swatch.pack(side="left", padx=Spacing.SM)

        var.trace_add("write", lambda *_: self._on_color_typed(var, swatch))
        return var

    def _on_color_typed(self, var, swatch):
        value = var.get().strip()
        if not _is_hex_color(value):
            return  # half-typed code; wait for the rest
        swatch.configure(fg_color=value)
        self._on_change()

    def _on_text_opacity(self, value):
        config.OVERLAY_TEXT_OPACITY = round(float(value), 2)
        self._on_change()

    def _on_bg_opacity(self, value):
        config.OVERLAY_BG_OPACITY = round(float(value), 2)
        self._on_change()

    def _on_font_size(self, value):
        config.OVERLAY_FONT_SIZE = int(round(float(value)))
        self._on_change()

    def _on_change(self):
        config.OVERLAY_ENABLED = self.enabled_var.get()
        config.OVERLAY_POSITION = self.position_var.get()
        for key, var in self.item_vars.items():
            config.OVERLAY_ITEMS[key] = var.get()

        for var, attr in ((getattr(self, "text_color_var", None), "OVERLAY_TEXT_COLOR"),
                          (getattr(self, "bg_color_var", None), "OVERLAY_BG_COLOR")):
            if var is not None and _is_hex_color(var.get().strip()):
                setattr(config, attr, var.get().strip())

        config.save()
        if self.on_overlay_changed:
            self.on_overlay_changed()

    def on_show(self):
        super().on_show()
        provider = get_fps_provider()
        # Touch the provider so an RTSS started after us is picked up.
        apps = provider.get_apps()
        if provider.available:
            if apps:
                names = ", ".join(a["name"] for a in apps[:3])
                self.lbl_fps_status.configure(text=t("overlay_fps_detected", names),
                                              text_color=Colors.SUCCESS)
            else:
                self.lbl_fps_status.configure(text=t("overlay_fps_idle"),
                                              text_color=Colors.TEXT_SECONDARY)
        else:
            self.lbl_fps_status.configure(text=t("overlay_fps_no_rtss"),
                                          text_color=Colors.WARNING)
