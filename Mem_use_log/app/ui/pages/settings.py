import customtkinter as ctk
from ui.pages.base_page import BasePage
from ui.theme import Colors, Spacing, get_typography
from config.settings import config
from i18n import t
from utils import autostart

LANGUAGE_LABELS = {"한국어": "ko", "English": "en"}
LANGUAGE_LABELS_REVERSE = {v: k for k, v in LANGUAGE_LABELS.items()}

class SettingsPage(BasePage):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)

        lbl = ctk.CTkLabel(self, text=t("settings_title"), font=get_typography().headline, text_color=Colors.PRIMARY)
        lbl.pack(anchor="w", padx=Spacing.MD, pady=Spacing.MD)

        # System Interval
        self.lbl_sys_interval = ctk.CTkLabel(self, text=t("system_interval"), font=get_typography().body_large, text_color=Colors.TEXT_PRIMARY)
        self.lbl_sys_interval.pack(anchor="w", padx=Spacing.MD, pady=(Spacing.MD, 0))

        self.sys_interval_var = ctk.StringVar(value=str(config.SYSTEM_COLLECTION_INTERVAL_MS))
        self.entry_sys_interval = ctk.CTkEntry(self, textvariable=self.sys_interval_var, width=200)
        self.entry_sys_interval.pack(anchor="w", padx=Spacing.MD, pady=Spacing.XS)

        # Export Dir
        self.lbl_export_dir = ctk.CTkLabel(self, text=t("export_directory"), font=get_typography().body_large, text_color=Colors.TEXT_PRIMARY)
        self.lbl_export_dir.pack(anchor="w", padx=Spacing.MD, pady=(Spacing.MD, 0))

        self.export_dir_var = ctk.StringVar(value=config.EXPORT_DIRECTORY)
        self.entry_export_dir = ctk.CTkEntry(self, textvariable=self.export_dir_var, width=400)
        self.entry_export_dir.pack(anchor="w", padx=Spacing.MD, pady=Spacing.XS)

        # Language
        self.lbl_language = ctk.CTkLabel(self, text=t("language"), font=get_typography().body_large, text_color=Colors.TEXT_PRIMARY)
        self.lbl_language.pack(anchor="w", padx=Spacing.MD, pady=(Spacing.MD, 0))

        self.language_var = ctk.StringVar(value=LANGUAGE_LABELS_REVERSE.get(config.LANGUAGE, "한국어"))
        self.option_language = ctk.CTkOptionMenu(self, variable=self.language_var, values=list(LANGUAGE_LABELS.keys()))
        self.option_language.pack(anchor="w", padx=Spacing.MD, pady=Spacing.XS)

        # Auto-start recording when app opens
        self.auto_start_var = ctk.BooleanVar(value=config.AUTO_START_RECORDING)
        self.chk_auto_start = ctk.CTkCheckBox(self, text=t("auto_start_recording"), variable=self.auto_start_var,
                                               font=get_typography().body_large, text_color=Colors.TEXT_PRIMARY)
        self.chk_auto_start.pack(anchor="w", padx=Spacing.MD, pady=(Spacing.MD, 0))

        # Start on Windows boot
        self.start_on_boot_var = ctk.BooleanVar(value=config.START_ON_BOOT)
        self.chk_start_on_boot = ctk.CTkCheckBox(self, text=t("start_on_boot"), variable=self.start_on_boot_var,
                                                  font=get_typography().body_large, text_color=Colors.TEXT_PRIMARY)
        self.chk_start_on_boot.pack(anchor="w", padx=Spacing.MD, pady=(Spacing.XS, 0))

        # Save Button
        self.btn_save = ctk.CTkButton(self, text=t("save_settings"), font=get_typography().body_large, command=self._save_settings)
        self.btn_save.pack(anchor="w", padx=Spacing.MD, pady=Spacing.LG)

        self.lbl_status = ctk.CTkLabel(self, text="", font=get_typography().body_medium, text_color=Colors.SUCCESS)
        self.lbl_status.pack(anchor="w", padx=Spacing.MD)

    def _save_settings(self):
        try:
            val_int = int(self.sys_interval_var.get())
            if val_int > 0:
                config.SYSTEM_COLLECTION_INTERVAL_MS = val_int
        except ValueError:
            pass

        config.EXPORT_DIRECTORY = self.export_dir_var.get()
        config.LANGUAGE = LANGUAGE_LABELS.get(self.language_var.get(), config.LANGUAGE)
        config.AUTO_START_RECORDING = self.auto_start_var.get()

        want_boot_start = self.start_on_boot_var.get()
        boot_start_ok = True
        if want_boot_start != config.START_ON_BOOT or want_boot_start != autostart.is_enabled():
            boot_start_ok = autostart.set_enabled(want_boot_start)
        if boot_start_ok:
            config.START_ON_BOOT = want_boot_start

        config.save()

        if boot_start_ok:
            self.lbl_status.configure(text=t("settings_saved"), text_color=Colors.SUCCESS)
        else:
            self.lbl_status.configure(text=t("settings_save_failed", "registry"), text_color=Colors.ERROR)
        self.after(4000, lambda: self.lbl_status.configure(text=""))
