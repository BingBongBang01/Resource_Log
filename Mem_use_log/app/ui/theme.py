import customtkinter as ctk

# Material Design 3 spacing scale
class Spacing:
    XS = 4
    SM = 8
    MD = 16
    LG = 24
    XL = 32
    XXL = 48

# Material Design 3 generic Semantic Colors (Dark mode optimized)
class Colors:
    PRIMARY = "#A8C7FA"       # MD3 Primary (Blue-ish)
    ON_PRIMARY = "#062E6F"
    
    SECONDARY = "#C2C7CF"     # MD3 Secondary
    ON_SECONDARY = "#2C3137"
    
    SURFACE = "#1E1F22"       # Dark surface
    SURFACE_CONTAINER = "#2B2D31" # Slightly lighter container
    SURFACE_CONTAINER_HIGH = "#313338" # Hover or active container
    
    OUTLINE = "#44474E"
    
    ERROR = "#FFB4AB"
    SUCCESS = "#81C995"
    WARNING = "#FDE293"
    NEUTRAL = "#E3E2E6"
    
    TEXT_PRIMARY = "#E3E2E6"
    TEXT_SECONDARY = "#C4C6D0"

class Typography:
    def __init__(self):
        # We instantiate CTkFont here so it's tied to the tk instance correctly
        # Fallback to standard fonts if specific ones aren't available
        base_font = "Segoe UI Variable Display" if ctk.get_appearance_mode() else "Segoe UI"
        
        self.display = ctk.CTkFont(family=base_font, size=32, weight="bold")
        self.headline = ctk.CTkFont(family=base_font, size=24, weight="bold")
        self.title = ctk.CTkFont(family=base_font, size=18, weight="bold")
        self.body_large = ctk.CTkFont(family=base_font, size=14, weight="normal")
        self.body_medium = ctk.CTkFont(family=base_font, size=13, weight="normal")
        self.label = ctk.CTkFont(family=base_font, size=11, weight="normal")

_theme = None

def get_typography() -> Typography:
    global _theme
    if _theme is None:
        _theme = Typography()
    return _theme
