"""Utility functions for widget rendering.

Provides agent color assignment and prefix formatting used across
multiple widget types for consistent visual attribution.

Concept: AU-018 (TUI Widget Utilities)
"""

# Muted/pastel colors for subagents — consistent assignment via hash
AGENT_COLORS: list[str] = [
    "#9db4c0",  # pale blue
    "#c9ada7",  # pale mauve
    "#a7c4a0",  # pale green
    "#d4a5a5",  # pale rose
    "#b8a9c9",  # pale lavender
    "#f0d9b5",  # pale peach
    "#87bdd8",  # soft blue
    "#d5c4a1",  # pale khaki
]


def get_agent_color(agent_name: str) -> str:
    """Return a consistent color for an agent based on its name.

    Uses a deterministic hash of the agent name to pick a stable color
    from the curated AGENT_COLORS palette.

    Args:
        agent_name: The identifier of the agent.

    Returns:
        A hex color string.
    """
    return AGENT_COLORS[hash(agent_name) % len(AGENT_COLORS)]


def format_agent_prefix(agent_name: str) -> str:
    """Return the agent name prefix for plain text display.

    Args:
        agent_name: The identifier of the agent.

    Returns:
        A formatted string like "(researcher) " or empty string for the main agent.
    """
    if agent_name == "main":
        return ""
    return f"({agent_name}) "


def format_agent_prefix_markup(agent_name: str) -> str:
    """Return the agent name prefix with Rich color markup.

    Args:
        agent_name: The identifier of the agent.

    Returns:
        A string with Rich markup, e.g., "[#a7c4a0](researcher)[/#a7c4a0] ".
    """
    if agent_name == "main":
        return ""
    color = get_agent_color(agent_name)
    return f"[{color}]({agent_name})[/{color}] "
