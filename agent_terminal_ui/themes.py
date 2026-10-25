"""Optional opaque terminal palettes registered with Textual's theme system."""

from textual.theme import Theme

CANOPY = Theme(
    name="canopy",
    primary="#ADC99F",
    secondary="#D0DBCB",
    accent="#D6C8AE",
    warning="#EDD08A",
    error="#F0B0A6",
    success="#B5D6A8",
    foreground="#F1F5EB",
    background="#121C17",
    surface="#1C2A22",
    panel="#27372D",
    dark=True,
    text_alpha=1.0,
    variables={
        "text-muted": "#AABAA5",
        "text-disabled": "#AABAA5",
        "foreground-muted": "#AABAA5",
        "foreground-disabled": "#AABAA5",
        "border": "#ADC99F",
        "border-blurred": "#829680",
        "block-cursor-background": "#ADC99F",
        "block-cursor-foreground": "#16251A",
        "input-selection-background": "#314A35",
        "input-selection-foreground": "#E4EEDC",
        "button-color-foreground": "#16251A",
        "footer-key-foreground": "#ADC99F",
    },
)
