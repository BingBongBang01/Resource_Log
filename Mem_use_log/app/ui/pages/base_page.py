import customtkinter as ctk

class BasePage(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        from ui.theme import Colors
        super().__init__(master, fg_color=Colors.SURFACE_CONTAINER, corner_radius=12, **kwargs)
        
    def on_show(self):
        """Called when the page is navigated to."""
        pass
        
    def on_hide(self):
        """Called when the page is navigated away from."""
        pass
