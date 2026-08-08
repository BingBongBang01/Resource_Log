import customtkinter as ctk
from ui.theme import Colors, Spacing, get_typography
from i18n import t
from typing import Callable

class NavigationRail(ctk.CTkFrame):
    def __init__(self, master, on_navigate: Callable[[str], None], **kwargs):
        super().__init__(master, fg_color=Colors.SURFACE, corner_radius=0, **kwargs)
        self.on_navigate = on_navigate
        self.buttons = {}
        self.current_selection = None

        self.grid_rowconfigure(0, weight=0) # Logo
        self.grid_rowconfigure(1, weight=1) # Spacer

        # Logo / Title
        self.logo = ctk.CTkLabel(self, text=t("logo"), font=get_typography().title, text_color=Colors.PRIMARY)
        self.logo.grid(row=0, column=0, padx=Spacing.MD, pady=Spacing.LG, sticky="ew")

        # Container for navigation items
        self.nav_container = ctk.CTkFrame(self, fg_color="transparent")
        self.nav_container.grid(row=1, column=0, sticky="n", padx=Spacing.XS)

        # Settings at bottom
        self.grid_rowconfigure(2, weight=0)
        self.settings_btn = self._create_nav_button("Settings", self.nav_container, display_name=t("nav_settings"))
        self.settings_btn.grid(row=2, column=0, padx=Spacing.XS, pady=Spacing.MD, sticky="ew")

    def _create_nav_button(self, name: str, parent, display_name: str = None) -> ctk.CTkButton:
        btn = ctk.CTkButton(
            self if name == "Settings" else parent,
            text=display_name or name,
            font=get_typography().body_large,
            fg_color="transparent",
            text_color=Colors.TEXT_PRIMARY,
            hover_color=Colors.SURFACE_CONTAINER_HIGH,
            anchor="w",
            height=40,
            command=lambda n=name: self._select_item(n)
        )
        return btn

    def add_destination(self, name: str, display_name: str = None):
        row = len(self.buttons)
        btn = self._create_nav_button(name, self.nav_container, display_name=display_name)
        btn.grid(row=row, column=0, pady=Spacing.XS, sticky="ew")
        self.buttons[name] = btn

    def _select_item(self, name: str):
        if self.current_selection == name:
            return
            
        # Reset previous
        if self.current_selection:
            prev_btn = self.buttons.get(self.current_selection) or (self.settings_btn if self.current_selection == "Settings" else None)
            if prev_btn:
                prev_btn.configure(fg_color="transparent", text_color=Colors.TEXT_PRIMARY)
                
        # Set new
        self.current_selection = name
        btn = self.buttons.get(name) or (self.settings_btn if name == "Settings" else None)
        if btn:
            btn.configure(fg_color=Colors.SURFACE_CONTAINER_HIGH, text_color=Colors.PRIMARY)
            
        self.on_navigate(name)

    def select(self, name: str):
        self._select_item(name)
