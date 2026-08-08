import customtkinter as ctk
from ui.theme import Colors, Spacing, get_typography

class MetricCard(ctk.CTkFrame):
    def __init__(self, master, title: str, value: str = "-", subtitle: str = "", **kwargs):
        super().__init__(master, fg_color=Colors.SURFACE_CONTAINER_HIGH, corner_radius=12, **kwargs)
        
        self.title_lbl = ctk.CTkLabel(self, text=title, font=get_typography().body_medium, text_color=Colors.TEXT_SECONDARY)
        self.title_lbl.pack(anchor="w", padx=Spacing.MD, pady=(Spacing.MD, 0))
        
        self.value_lbl = ctk.CTkLabel(self, text=value, font=get_typography().headline, text_color=Colors.TEXT_PRIMARY)
        self.value_lbl.pack(anchor="w", padx=Spacing.MD, pady=(Spacing.XS, 0))
        
        self.subtitle_lbl = ctk.CTkLabel(self, text=subtitle, font=get_typography().label, text_color=Colors.TEXT_SECONDARY)
        self.subtitle_lbl.pack(anchor="w", padx=Spacing.MD, pady=(0, Spacing.MD))
        
    def set_value(self, value: str, subtitle: str = None):
        self.value_lbl.configure(text=value)
        if subtitle is not None:
            self.subtitle_lbl.configure(text=subtitle)

class ResourceCard(ctk.CTkFrame):
    def __init__(self, master, title: str, primary_val: str, secondary_val: str, tertiary_val: str = "", **kwargs):
        super().__init__(master, fg_color=Colors.SURFACE_CONTAINER_HIGH, corner_radius=12, **kwargs)
        
        self.grid_columnconfigure(0, weight=1)
        
        lbl_title = ctk.CTkLabel(self, text=title, font=get_typography().title, text_color=Colors.PRIMARY)
        lbl_title.grid(row=0, column=0, sticky="w", padx=Spacing.MD, pady=(Spacing.MD, Spacing.XS))
        
        self.lbl_primary = ctk.CTkLabel(self, text=primary_val, font=get_typography().headline, text_color=Colors.TEXT_PRIMARY)
        self.lbl_primary.grid(row=1, column=0, sticky="w", padx=Spacing.MD)
        
        self.lbl_secondary = ctk.CTkLabel(self, text=secondary_val, font=get_typography().body_large, text_color=Colors.TEXT_SECONDARY)
        self.lbl_secondary.grid(row=2, column=0, sticky="w", padx=Spacing.MD, pady=(0, Spacing.XS))
        
        self.lbl_tertiary = ctk.CTkLabel(self, text=tertiary_val, font=get_typography().body_medium, text_color=Colors.TEXT_SECONDARY)
        self.lbl_tertiary.grid(row=3, column=0, sticky="w", padx=Spacing.MD, pady=(0, Spacing.MD))
        
    def update_data(self, primary: str, secondary: str, tertiary: str = None):
        self.lbl_primary.configure(text=primary)
        self.lbl_secondary.configure(text=secondary)
        if tertiary is not None:
            self.lbl_tertiary.configure(text=tertiary)
