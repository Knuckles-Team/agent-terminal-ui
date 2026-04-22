#!/usr/bin/python
"""Theme configuration system for Agent Terminal UI.

This module provides theme presets following modern terminal UI design principles:
- Color restraint: 1 primary accent + semantic colors only
- Semantic meaning: colors communicate state, not decoration
- Calm aesthetic: minimal distractions, focus on content
- Accessibility: proper contrast ratios for both dark and light modes
- Terminal transparency: Respects user's terminal background by default
"""

from dataclasses import dataclass


@dataclass
class ThemeColors:
    """Color palette for a theme following restraint principles.

    Uses minimal active colors with semantic meaning:
    - 1 primary accent for user input and focus
    - Semantic colors for success, warning, error states
    - Neutral grays for structure and hierarchy
    """

    # Base colors (transparent to respect user's terminal background)
    background: str  # Transparent by default
    foreground: str
    surface: str  # Secondary background for panels/cards

    # Semantic colors (state communication, not decoration)
    primary: str  # Single accent for user input, focus, active elements
    success: str  # Completed states, successful operations
    warning: str  # Cautionary states, needs attention
    error: str  # Error states, failures, destructive actions
    info: str  # Informational states, neutral highlights

    # UI structure colors (neutral hierarchy)
    border: str
    divider: str
    muted: str  # Secondary text, metadata
    subtle: str  # Very subtle for metadata that should disappear

    # Input colors
    input_background: str  # Can be transparent or semi-transparent
    input_foreground: str

    # Sidebar colors
    sidebar_background: str  # Can be transparent or semi-transparent
    sidebar_foreground: str  # Text color for sidebar content


@dataclass
class ThemeConfig:
    """Complete theme configuration with restraint principles."""

    name: str
    colors: ThemeColors

    # Typography settings
    font_family: str = "JetBrains Mono, Fira Code, monospace"
    font_size: int = 14
    line_height: float = 1.5

    # Spacing scale (in characters)
    spacing_xs: int = 1
    spacing_sm: int = 2
    spacing_md: int = 3
    spacing_lg: int = 4
    spacing_xl: int = 6

    # UI behavior
    animations_enabled: bool = True  # Subtle animations only
    gradient_enabled: bool = False  # Disabled for calm aesthetic
    powerline_enabled: bool = False  # Disabled for minimal aesthetic
    rounded_corners: bool = True

    # Icon policy: minimal, functional only
    icons_enabled: bool = False

    # Icon mappings (minimal, text-based where possible)
    icons: dict[str, str] | None = None

    def __post_init__(self):
        """Set default minimal icons if not provided."""
        if self.icons is None:
            self.icons = {
                "active": "▶",  # Active/running state
                "completed": "✓",  # Completed state
                "pending": " ",  # Pending state (space)
                "error": "✕",  # Error state
                "warning": "!",  # Warning state
                "info": "i",  # Info state
            }


# Modern Dark Theme (Default) - Restrained palette with semantic meaning
MODERN_DARK = ThemeConfig(
    name="modern_dark",
    colors=ThemeColors(
        # Base colors (transparent to respect user's terminal background)
        background="rgba(0,0,0,0)",  # Fully transparent to respect terminal background
        foreground="#a9b1d6",  # Light blue-gray for text
        surface="#1a1b26",  # Semi-transparent surface for panels
        # Single primary accent (blue for focus/input)
        primary="#7aa2f7",  # Muted blue
        # Semantic colors (state communication)
        success="#9ece6a",  # Green for completed/success
        warning="#e0af68",  # Orange for warnings
        error="#f7768e",  # Red for errors
        info="#7dcfff",  # Cyan for information
        # UI structure (neutral hierarchy)
        border="#414868",  # Subtle border
        divider="#565f89",  # Slightly more visible for dividers
        muted="#787c99",  # Secondary text
        subtle="#565f89",  # Very subtle metadata
        # Input colors
        input_background="rgba(0,0,0,0)",  # Fully transparent
        input_foreground="#a9b1d6",
        # Sidebar colors
        sidebar_background="rgba(0,0,0,0)",  # Fully transparent
        sidebar_foreground="#9aa5ce",
    ),
    animations_enabled=True,
    gradient_enabled=False,
    powerline_enabled=False,
    rounded_corners=True,
    icons_enabled=False,
)


# Modern Light Theme - First-class light mode with proper contrast
MODERN_LIGHT = ThemeConfig(
    name="modern_light",
    colors=ThemeColors(
        # Base colors (transparent to respect user's terminal background)
        background="rgba(0,0,0,0)",  # Fully transparent to respect terminal background
        foreground="#37474f",  # Dark blue-gray for text
        surface="#fafafa",  # Semi-transparent surface for panels
        # Single primary accent (blue for focus/input)
        primary="#1976d2",  # Muted blue
        # Semantic colors (state communication)
        success="#388e3c",  # Green for completed/success
        warning="#f57c00",  # Orange for warnings
        error="#d32f2f",  # Red for errors
        info="#0288d1",  # Blue for information
        # UI structure (neutral hierarchy)
        border="#cfd8dc",  # Subtle border
        divider="#eceff1",  # Slightly more visible for dividers
        muted="#78909c",  # Secondary text
        subtle="#cfd8dc",  # Very subtle metadata
        # Input colors
        input_background="rgba(0,0,0,0)",  # Fully transparent
        input_foreground="#37474f",
        # Sidebar colors
        sidebar_background="rgba(0,0,0,0)",  # Fully transparent
        sidebar_foreground="#455a64",
    ),
    animations_enabled=True,
    gradient_enabled=False,
    powerline_enabled=False,
    rounded_corners=True,
    icons_enabled=False,
)


# Nord Theme - Adapted for restraint principles
NORD = ThemeConfig(
    name="nord",
    colors=ThemeColors(
        # Base colors (transparent to respect user's terminal background)
        background="rgba(0,0,0,0)",  # Fully transparent to respect terminal background
        foreground="#eceff4",  # Nord light
        surface="#2e3440",  # Semi-transparent surface for panels
        # Single primary accent (Nord blue)
        primary="#88c0d0",  # Nord frost blue
        # Semantic colors (Nord aurora)
        success="#a3be8c",  # Nord aurora green
        warning="#ebcb8b",  # Nord aurora yellow
        error="#bf616a",  # Nord aurora red
        info="#8fbcbb",  # Nord aurora cyan
        # UI structure (Nord polar)
        border="#4c566a",  # Nord polar
        divider="#434c5e",  # Nord polar darker
        muted="#d8dee9",  # Nord snow storm
        subtle="#4c566a",  # Very subtle
        # Input colors
        input_background="rgba(0,0,0,0)",  # Fully transparent
        input_foreground="#eceff4",
        # Sidebar colors
        sidebar_background="rgba(0,0,0,0)",  # Fully transparent
        sidebar_foreground="#d8dee9",
    ),
    animations_enabled=False,
    gradient_enabled=False,
    powerline_enabled=False,
    rounded_corners=False,
    icons_enabled=False,
)


# Gruvbox Theme - Adapted for restraint principles
GRUVBOX = ThemeConfig(
    name="gruvbox",
    colors=ThemeColors(
        # Base colors (transparent to respect user's terminal background)
        background="rgba(0,0,0,0)",  # Fully transparent to respect terminal background
        foreground="#ebdbb2",  # Gruvbox fg
        surface="#282828",  # Semi-transparent surface for panels
        # Single primary accent (Gruvbox blue)
        primary="#83a598",  # Gruvbox blue
        # Semantic colors (Gruvbox palette)
        success="#b8bb26",  # Gruvbox green
        warning="#d79921",  # Gruvbox yellow
        error="#fb4934",  # Gruvbox red
        info="#8ec07c",  # Gruvbox aqua
        # UI structure (Gruvbox gray)
        border="#504945",  # Gruvbox gray
        divider="#3c3836",  # Gruvbox bg1
        muted="#928374",  # Gruvbox gray
        subtle="#504945",  # Very subtle
        # Input colors
        input_background="rgba(0,0,0,0)",  # Fully transparent
        input_foreground="#ebdbb2",
        # Sidebar colors
        sidebar_background="rgba(0,0,0,0)",  # Fully transparent
        sidebar_foreground="#d5c4a1",
    ),
    animations_enabled=True,
    gradient_enabled=False,
    powerline_enabled=False,
    rounded_corners=True,
    icons_enabled=False,
)

# Available themes registry
AVAILABLE_THEMES: dict[str, ThemeConfig] = {
    "modern_dark": MODERN_DARK,
    "modern_light": MODERN_LIGHT,
    "nord": NORD,
    "gruvbox": GRUVBOX,
}

DEFAULT_THEME = MODERN_DARK


def get_theme(theme_name: str) -> ThemeConfig:
    """Get a theme configuration by name.

    Args:
        theme_name: The name of the theme to retrieve.

    Returns:
        The ThemeConfig for the requested theme, or default if not found.
    """
    return AVAILABLE_THEMES.get(theme_name.lower(), DEFAULT_THEME)


def list_themes() -> list[str]:
    """List all available theme names.

    Returns:
        A list of available theme names.
    """
    return list(AVAILABLE_THEMES.keys())


def generate_css_from_theme(theme: ThemeConfig) -> str:
    """Generate CSS from a theme configuration following restraint principles.

    Args:
        theme: The theme configuration to generate CSS from.

    Returns:
        A CSS string with theme-specific colors and styles following modern
        terminal UI guidelines (restraint, semantic colors, calm aesthetic).
    """
    c = theme.colors

    css = f"""
/* Theme: {theme.name} - Following restraint principles */
Screen {{
    background: {c.background};
    color: {c.foreground};
}}

/* RichLog - Main content area with minimal styling */
RichLog {{
    background: {c.background};
    scrollbar-background: {c.background};
    scrollbar-color: {c.border};
    scrollbar-color-hover: {c.muted};
}}

/* InputTextArea - Clean input with semantic focus state */
InputTextArea {{
    background: {c.input_background};
    color: {c.input_foreground};
    border-top: solid {c.border};
    border-bottom: solid {c.border};
    &>.text-area--cursor-line {{
        background: {c.primary} 3%;
    }}
    &:focus {{
        border-top: solid {c.border};
        border-bottom: solid {c.border};
    }}
}}

/* StatusLine - Minimal status indicators */
StatusLine {{
    background: {c.background};
    border-top: solid {c.border};
}}

/* WorkflowSidebar - Structured workflow visualization */
WorkflowSidebar {{
    background: {c.sidebar_background};
    border-left: solid {c.border};
    & WorkflowNode {{
        background: {c.background};
        border: solid {c.border};
        color: {c.sidebar_foreground};
    }}
    & WorkflowNode.completed {{
        background: {c.background};
        border: solid {c.success};
        color: {c.success};
    }}
    & WorkflowNode.active {{
        background: {c.background};
        border: solid {c.primary};
        color: {c.primary};
    }}
}}

/* Buttons - Semantic styling */
Button {{
    background: {c.primary};
    color: {c.background};
    &.-error {{
        background: {c.error};
    }}
    &.-primary {{
        background: {c.success};
    }}
}}

/* Tool displays - Clean card styling */
ToolCallDisplay {{
    background: {c.background};
    border: solid {c.border};
    border-left: solid {c.primary};
}}

ToolOutputDisplay {{
    background: {c.background};
    border: solid {c.border};
    border-left: solid {c.success};
}}
"""
    return css
