"""Reasoning effort tiers and auto model routing.

Concept: TUI-3 (Reasoning Effort)
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ReasoningEffortTier(Enum):
    """Reasoning effort levels, modeled after DeepSeek-TUI."""

    OFF = "off"
    HIGH = "high"
    MAX = "max"

    def next(self) -> ReasoningEffortTier:
        """Cycle to the next tier: OFF -> HIGH -> MAX -> OFF."""
        cycle = [
            ReasoningEffortTier.OFF,
            ReasoningEffortTier.HIGH,
            ReasoningEffortTier.MAX,
        ]
        idx = cycle.index(self)
        return cycle[(idx + 1) % len(cycle)]

    @property
    def display_icon(self) -> str:
        """Return a display icon for the status line."""
        return {"off": "", "high": "⚡", "max": "⚡⚡"}.get(self.value, "")

    @property
    def display_label(self) -> str:
        """Return a human-readable label."""
        return {
            "off": "Thinking: Off",
            "high": "Thinking: High",
            "max": "Thinking: Max",
        }.get(self.value, "Thinking: Off")


class AutoRouteDecision:
    """Result of an auto-routing decision."""

    def __init__(
        self, model: str, reasoning_effort: ReasoningEffortTier, rationale: str = ""
    ) -> None:
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.rationale = rationale

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "reasoning_effort": self.reasoning_effort.value,
            "rationale": self.rationale,
        }


_COMPLEX_KEYWORDS = frozenset(
    {
        "debug",
        "fix",
        "refactor",
        "architect",
        "security",
        "review",
        "migration",
        "optimize",
        "performance",
        "design",
        "implement",
        "integrate",
        "deploy",
        "release",
        "test",
        "benchmark",
    }
)
_SIMPLE_KEYWORDS = frozenset(
    {
        "explain",
        "what",
        "how",
        "summarize",
        "list",
        "show",
        "help",
        "hello",
        "hi",
        "thanks",
    }
)


class AutoModelRouter:
    """Routes queries to the optimal model and reasoning effort."""

    def __init__(
        self,
        fast_model: str = "flash",
        pro_model: str = "pro",
        default_model: str = "default",
    ) -> None:
        self._fast_model = fast_model
        self._pro_model = pro_model
        self._default_model = default_model

    def route(
        self, query: str, context_turns: int = 0, mode: str = "ask"
    ) -> AutoRouteDecision:
        """Route a query to the optimal model and reasoning effort.

        Args:
            query: The user's query text.
            context_turns: Number of turns in the current context.
            mode: The current interaction mode.
        """
        words = set(query.lower().split())
        query_len = len(query)

        if mode in ("plan", "code", "build"):
            return AutoRouteDecision(
                self._pro_model,
                ReasoningEffortTier.HIGH,
                f"Mode '{mode}' defaults to pro",
            )
        complex_hits = words & _COMPLEX_KEYWORDS
        simple_hits = words & _SIMPLE_KEYWORDS
        if complex_hits and query_len > 100:
            return AutoRouteDecision(
                self._pro_model, ReasoningEffortTier.MAX, "Complex + long query"
            )
        if complex_hits:
            return AutoRouteDecision(
                self._pro_model,
                ReasoningEffortTier.HIGH,
                f"Complex keywords: {', '.join(complex_hits)}",
            )
        if simple_hits and query_len < 50:
            return AutoRouteDecision(
                self._fast_model, ReasoningEffortTier.OFF, "Simple query"
            )
        if context_turns > 10:
            return AutoRouteDecision(
                self._pro_model,
                ReasoningEffortTier.HIGH,
                f"Extended conversation ({context_turns} turns)",
            )
        return AutoRouteDecision(
            self._default_model, ReasoningEffortTier.HIGH, "Default balanced routing"
        )


class ReasoningEffortManager:
    """Manages reasoning effort state and cycling for the TUI."""

    def __init__(
        self,
        initial_tier: ReasoningEffortTier = ReasoningEffortTier.HIGH,
        auto_mode: bool = False,
    ) -> None:
        self._current_tier = initial_tier
        self._auto_mode = auto_mode
        self._router = AutoModelRouter()

    @property
    def current_tier(self) -> ReasoningEffortTier:
        return self._current_tier

    @current_tier.setter
    def current_tier(self, tier: ReasoningEffortTier) -> None:
        self._current_tier = tier

    @property
    def auto_mode(self) -> bool:
        return self._auto_mode

    @auto_mode.setter
    def auto_mode(self, enabled: bool) -> None:
        self._auto_mode = enabled

    def cycle(self) -> ReasoningEffortTier:
        """Cycle to the next reasoning tier."""
        self._current_tier = self._current_tier.next()
        return self._current_tier

    def route_query(
        self, query: str, context_turns: int = 0, mode: str = "ask"
    ) -> AutoRouteDecision:
        """Route a query through auto-mode or return current settings."""
        if self._auto_mode:
            return self._router.route(query, context_turns, mode)
        return AutoRouteDecision(
            "default", self._current_tier, "Manual reasoning effort setting"
        )

    def get_status_display(self) -> str:
        """Get the status line display string."""
        if self._auto_mode:
            return "[cyan]Auto[/cyan]"
        if self._current_tier == ReasoningEffortTier.OFF:
            return "[dim]Think: Off[/dim]"
        elif self._current_tier == ReasoningEffortTier.HIGH:
            return "[yellow]⚡ High[/yellow]"
        return "[bold yellow]⚡⚡ Max[/bold yellow]"
