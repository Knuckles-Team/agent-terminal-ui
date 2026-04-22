#!/usr/bin/python
"""CSS styles for the Agent Terminal UI.

This module contains the global stylesheet for the Textual-based
terminal application, defining the visual appearance with modern
terminal UI design principles:
- Restraint: Minimal colors, semantic meaning only
- Typography: Clear hierarchy with spacing system
- Vertical rhythm: Intentional spacing for structure
- Calm aesthetic: Focus on content over decoration
"""

# Spacing scale (in characters) following 8pt grid system
SPACING_XS = 1  # 8pt
SPACING_SM = 2  # 16pt
SPACING_MD = 3  # 24pt
SPACING_LG = 4  # 32pt
SPACING_XL = 6  # 48pt

# Typography scale
FONT_FAMILY = "JetBrains Mono, Fira Code, monospace"
FONT_SIZE_BASE = 14
LINE_HEIGHT = 1.5

# Color palette (will be overridden by theme)
PRIMARY = "#7aa2f7"
SUCCESS = "#9ece6a"
WARNING = "#e0af68"
ERROR = "#f7768e"
MUTED = "#787c99"
SUBTLE = "#565f89"

AGENT_APP_CSS: str = f"""
/* Global Styles - Following restraint principles */
Screen {{
    background: $background;
    color: $foreground;
}}

/* RichLog - Main content area with vertical rhythm */
RichLog {{
    height: 1fr;
    background: $background;
    border: none;
    padding: {SPACING_MD} {SPACING_SM} {SPACING_MD} {SPACING_SM};
    scrollbar-background: $background;
    scrollbar-color: $border;
    scrollbar-color-hover: $text-muted;
    scrollbar-gutter: stable;
    overflow-x: hidden;
}}

/* RichLog content spacing */
RichLog > .rich-log--container {{
    margin-bottom: {SPACING_SM};
}}

/* Input Area - Clean input with semantic focus state */
InputTextArea {{
    margin: 0 {SPACING_SM} 0 {SPACING_SM};
    height: auto;
    max-height: 10;
    background: $background;
    color: $foreground;
    border: none;
    border-top: solid $border;
    border-bottom: solid $border;
    padding: {SPACING_SM};

    &>.text-area--cursor-line {{
        background: $primary 5%;
    }}

    &>.text-area {{
        color: $foreground;
    }}

    &:focus {{
        /* Keep the same border color on focus to avoid blue line */
        border-top: solid $border;
        border-bottom: solid $border;
    }}
}}

/* Status Line - Minimal status indicators with clear hierarchy */
StatusLine {{
    dock: bottom;
    height: 1;
    margin: 0;
    padding: 0;
    background: $background;
    border-top: solid $border;

    & Static {{
        padding: 0 {SPACING_XS} 0 {SPACING_XS};
        text-style: bold;
    }}
}}

/* Status line segments with semantic meaning */
#status-mode {{
    color: $primary;
    text-style: bold;
}}

#status-model {{
    color: $foreground;
}}

#status-tokens {{
    color: $text-muted;
}}

#status-thinking {{
    color: $warning;
}}

/* Agent Timer - Subtle processing indicator */
AgentTimer {{
    height: auto;
    margin: 0 {SPACING_SM} 0 {SPACING_SM};
    padding: {SPACING_XS} {SPACING_SM};
    background: $success;
    border: none;

    & Static {{
        color: $background;
        text-style: bold;
        text-align: center;
    }}
}}

/* Workflow Sidebar - Structured with vertical rhythm */
WorkflowSidebar {{
    background: $background;
    border-left: solid $border;
    padding: {SPACING_MD};

    & WorkflowNode {{
        background: $background;
        border: solid $border;
        padding: {SPACING_SM};
        margin: 0 0 {SPACING_SM} 0;
        color: $foreground;

        &:hover {{
            background: $background;
            border: solid $primary;
        }}
    }}

    & WorkflowNode.completed {{
        background: $background;
        border: solid $success;
        color: $success;
    }}

    & WorkflowNode.active {{
        background: $background;
        border: solid $primary;
        color: $primary;
    }}

    /* Phase labels with clear hierarchy */
    & .phase-label {{
        color: $primary;
        text-style: bold;
        margin: {SPACING_MD} 0 {SPACING_SM} 0;
    }}
}}

/* Buttons - Semantic styling with clear hierarchy */
Button {{
    background: $primary;
    color: $background;
    border: none;
    padding: {SPACING_XS} {SPACING_MD};
    text-style: bold;
    margin: {SPACING_XS};

    &:hover {{
        background: $primary;
        opacity: 0.8;
    }}

    &.-error {{
        background: $error;
        &:hover {{
            background: $error;
            opacity: 0.8;
        }}
    }}

    &.-primary {{
        background: $success;
        &:hover {{
            background: $success;
            opacity: 0.8;
        }}
    }}
}}

/* Modal/Screen styling with spacing */
Screen {{
    background: $background;

    & Vertical {{
        padding: {SPACING_LG};
    }}

    & Label {{
        color: $foreground;
        text-align: center;
        padding: {SPACING_SM};
        margin-bottom: {SPACING_SM};
    }}
}}

/* Tool Call Display - Clean card styling with spacing */
ToolCallDisplay {{
    background: $background;
    border: solid $border;
    border-left: solid $primary;
    padding: {SPACING_SM};
    margin: 0 0 {SPACING_SM} 0;
}}

ToolOutputDisplay {{
    background: $background;
    border: solid $border;
    border-left: solid $success;
    padding: {SPACING_SM};
    margin: 0 0 {SPACING_SM} 0;
}}

/* Semantic color utilities - Minimal, purposeful */
.bold-primary {{
    color: $primary;
    text-style: bold;
}}

.bold-success {{
    color: $success;
    text-style: bold;
}}

.bold-warning {{
    color: $warning;
    text-style: bold;
}}

.bold-error {{
    color: $error;
    text-style: bold;
}}

/* Typography hierarchy utilities */
.muted {{
    color: $text-muted;
    text-style: dim;
}}

.subtle {{
    color: $text-disabled;
    text-style: dim;
}}

/* Semantic backgrounds with restraint */
.success {{
    color: $success;
    background: $success 10%;
    padding: 0 {SPACING_XS};
}}

.warning {{
    color: $warning;
    background: $warning 10%;
    padding: 0 {SPACING_XS};
}}

.error {{
    color: $error;
    background: $error 10%;
    padding: 0 {SPACING_XS};
}}

/* Enhanced typography with hierarchy */
Static, Label {{
}}
"""
