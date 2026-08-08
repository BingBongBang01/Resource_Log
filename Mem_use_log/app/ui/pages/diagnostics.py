import customtkinter as ctk
from ui.pages.base_page import BasePage
from ui.theme import Colors, Spacing, get_typography
from ui.state_manager import app_state
from i18n import t

class DiagnosticsPage(BasePage):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)

        lbl = ctk.CTkLabel(self, text=t("logger_diagnostics"), font=get_typography().headline, text_color=Colors.PRIMARY)
        lbl.pack(anchor="w", padx=Spacing.MD, pady=Spacing.MD)

        self.lbl_recording = ctk.CTkLabel(self, text=t("recording_label", "?"), font=get_typography().body_large, text_color=Colors.TEXT_PRIMARY)
        self.lbl_recording.pack(anchor="w", padx=Spacing.MD, pady=Spacing.XS)

        self.lbl_queue = ctk.CTkLabel(self, text=t("queue_size_label", 0), font=get_typography().body_large, text_color=Colors.TEXT_PRIMARY)
        self.lbl_queue.pack(anchor="w", padx=Spacing.MD, pady=Spacing.XS)

        self.lbl_last_write = ctk.CTkLabel(self, text=t("last_write_label", "N/A"), font=get_typography().body_large, text_color=Colors.TEXT_PRIMARY)
        self.lbl_last_write.pack(anchor="w", padx=Spacing.MD, pady=Spacing.XS)

        app_state.add_listener("recording_state", lambda v: self.lbl_recording.configure(text=t("recording_label", v.upper())))
        app_state.add_listener("queue_size", lambda v: self.lbl_queue.configure(text=t("queue_size_label", v)))
        app_state.add_listener("last_write", lambda v: self.lbl_last_write.configure(text=t("last_write_label", v)))
