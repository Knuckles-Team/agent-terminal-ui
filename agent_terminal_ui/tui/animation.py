"""Small, reusable entrance animation for conversation widgets.

Keeps the motion language consistent across message blocks: a new block fades
in on mount. Honors the app's animation level, so when animations are disabled
(e.g. ``TEXTUAL_ANIMATIONS=none`` in snapshot tests or reduced-motion
environments) widgets render immediately at their resting state.
"""

from __future__ import annotations

from textual.widget import Widget

ENTER_DURATION = 0.28
ENTER_EASING = "out_cubic"


def animate_in(widget: Widget) -> None:
    """Fade ``widget`` into view on mount.

    Args:
        widget: The freshly mounted widget to animate.
    """
    if getattr(widget.app, "animation_level", "full") == "none":
        return
    widget.styles.opacity = 0.0
    widget.styles.animate("opacity", 1.0, duration=ENTER_DURATION, easing=ENTER_EASING)
