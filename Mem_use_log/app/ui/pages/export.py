import customtkinter as ctk
import os
import threading
from ui.pages.base_page import BasePage
from ui.theme import Colors, Spacing, get_typography
from i18n import t

class ExportPage(BasePage):
    def __init__(self, master, db_instance, **kwargs):
        super().__init__(master, **kwargs)
        self.db = db_instance

        lbl = ctk.CTkLabel(self, text=t("export_data"), font=get_typography().headline, text_color=Colors.PRIMARY)
        lbl.pack(anchor="w", padx=Spacing.MD, pady=Spacing.MD)

        self.btn_export = ctk.CTkButton(self, text=t("export_to_csv"), font=get_typography().body_large, command=self._start_export)
        self.btn_export.pack(anchor="w", padx=Spacing.MD, pady=Spacing.MD)

        self.lbl_status = ctk.CTkLabel(self, text="", font=get_typography().body_medium, text_color=Colors.TEXT_SECONDARY)
        self.lbl_status.pack(anchor="w", padx=Spacing.MD, pady=Spacing.MD)

    def _start_export(self):
        self.lbl_status.configure(text=t("exporting"), text_color=Colors.WARNING)
        self.btn_export.configure(state="disabled")
        threading.Thread(target=self._export_worker, daemon=True).start()
        
    def _export_worker(self):
        from analyzer.report import CSVExporter
        from config.settings import config
        from datetime import datetime
        
        exporter = CSVExporter(self.db)
        export_dir = config.EXPORT_DIRECTORY
        os.makedirs(export_dir, exist_ok=True)
        
        timestamp_str = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        export_path = os.path.join(export_dir, f"system_log_{timestamp_str}.csv")
        
        success = exporter.export_system_data(export_path)
        
        def _update_ui():
            self.btn_export.configure(state="normal")
            if success:
                self.lbl_status.configure(text=t("export_success", export_path), text_color=Colors.SUCCESS)
            else:
                self.lbl_status.configure(text=t("export_failed"), text_color=Colors.ERROR)
                
        self.after(0, _update_ui)
