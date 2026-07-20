"""Per-turn cost and token tracking with session aggregation.

Tracks input/output/cached/reasoning tokens per turn, computes cost
via a configurable pricing registry, and provides session-level
aggregation with grouping by model or day.

Concept: TUI-10 (Cost Tracking)
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Default pricing per million tokens (USD)
DEFAULT_PRICING: dict[str, dict[str, float]] = {
    "default": {"input": 0.15, "output": 0.60, "cached": 0.075},
    "flash": {"input": 0.07, "output": 0.30, "cached": 0.035},
    "pro": {"input": 0.30, "output": 1.20, "cached": 0.15},
    "deepseek-v4-flash": {"input": 0.07, "output": 0.30, "cached": 0.035},
    "deepseek-v4-pro": {"input": 0.30, "output": 1.20, "cached": 0.15},
    "gpt-4o": {"input": 2.50, "output": 10.00, "cached": 1.25},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60, "cached": 0.075},
    "claude-sonnet": {"input": 3.00, "output": 15.00, "cached": 1.50},
    "claude-haiku": {"input": 0.25, "output": 1.25, "cached": 0.125},
}


@dataclass
class TurnUsage:
    """Token usage for a single turn."""

    turn_number: int = 0
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    reasoning_tokens: int = 0
    cost_usd: float = 0.0
    timestamp: float = field(default_factory=time.time)
    duration_ms: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def cache_hit_rate(self) -> float:
        if self.input_tokens == 0:
            return 0.0
        return self.cached_tokens / self.input_tokens

    def to_dict(self) -> dict[str, Any]:
        return {
            "turn_number": self.turn_number,
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cached_tokens": self.cached_tokens,
            "reasoning_tokens": self.reasoning_tokens,
            "total_tokens": self.total_tokens,
            "cost_usd": round(self.cost_usd, 6),
            "cache_hit_rate": round(self.cache_hit_rate, 2),
            "duration_ms": self.duration_ms,
        }


@dataclass
class SessionUsageSummary:
    """Aggregated usage across a session."""

    total_turns: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cached_tokens: int = 0
    total_reasoning_tokens: int = 0
    total_cost_usd: float = 0.0
    total_duration_ms: int = 0
    by_model: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return self.total_input_tokens + self.total_output_tokens

    @property
    def avg_cache_hit_rate(self) -> float:
        if self.total_input_tokens == 0:
            return 0.0
        return self.total_cached_tokens / self.total_input_tokens

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_turns": self.total_turns,
            "total_tokens": self.total_tokens,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_cached_tokens": self.total_cached_tokens,
            "total_reasoning_tokens": self.total_reasoning_tokens,
            "total_cost_usd": round(self.total_cost_usd, 6),
            "avg_cache_hit_rate": round(self.avg_cache_hit_rate, 2),
            "total_duration_ms": self.total_duration_ms,
            "by_model": self.by_model,
        }


class CostTracker:
    """Tracks per-turn token usage and cost with session aggregation.

    Uses a configurable pricing registry to compute costs. Supports
    grouping by model and provides cache hit/miss breakdowns.
    """

    def __init__(self, pricing: dict[str, dict[str, float]] | None = None) -> None:
        """Initialize the cost tracker.

        Args:
            pricing: Custom pricing registry (model -> {input, output, cached}
                per M tokens).
        """
        self._pricing = pricing or dict(DEFAULT_PRICING)
        self._turns: list[TurnUsage] = []

    @property
    def turns(self) -> list[TurnUsage]:
        return self._turns

    def set_pricing(
        self,
        model: str,
        input_per_m: float,
        output_per_m: float,
        cached_per_m: float = 0.0,
    ) -> None:
        """Set pricing for a model.

        Args:
            model: Model identifier.
            input_per_m: Input cost per million tokens.
            output_per_m: Output cost per million tokens.
            cached_per_m: Cached input cost per million tokens.
        """
        self._pricing[model] = {
            "input": input_per_m,
            "output": output_per_m,
            "cached": cached_per_m,
        }

    def compute_cost(
        self, model: str, input_tokens: int, output_tokens: int, cached_tokens: int = 0
    ) -> float:
        """Compute cost for a turn.

        Args:
            model: Model identifier.
            input_tokens: Number of input tokens.
            output_tokens: Number of output tokens.
            cached_tokens: Number of cached input tokens.

        Returns:
            Cost in USD.
        """
        prices = self._pricing.get(model, self._pricing.get("default", {}))
        if not prices:
            return 0.0

        billable_input = max(0, input_tokens - cached_tokens)
        cost = (
            (billable_input / 1_000_000) * prices.get("input", 0)
            + (output_tokens / 1_000_000) * prices.get("output", 0)
            + (cached_tokens / 1_000_000) * prices.get("cached", 0)
        )
        return cost

    def record_turn(
        self,
        turn_number: int,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cached_tokens: int = 0,
        reasoning_tokens: int = 0,
        duration_ms: int = 0,
    ) -> TurnUsage:
        """Record token usage for a turn.

        Args:
            turn_number: The turn number.
            model: Model identifier.
            input_tokens: Input token count.
            output_tokens: Output token count.
            cached_tokens: Cached input token count.
            reasoning_tokens: Reasoning/thinking token count.
            duration_ms: Turn duration in milliseconds.

        Returns:
            The recorded turn usage.
        """
        cost = self.compute_cost(model, input_tokens, output_tokens, cached_tokens)
        usage = TurnUsage(
            turn_number=turn_number,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=cached_tokens,
            reasoning_tokens=reasoning_tokens,
            cost_usd=cost,
            duration_ms=duration_ms,
        )
        self._turns.append(usage)
        return usage

    def get_session_summary(self) -> SessionUsageSummary:
        """Get aggregated usage summary for the current session."""
        summary = SessionUsageSummary()
        by_model: dict[str, dict[str, Any]] = {}

        for turn in self._turns:
            summary.total_turns += 1
            summary.total_input_tokens += turn.input_tokens
            summary.total_output_tokens += turn.output_tokens
            summary.total_cached_tokens += turn.cached_tokens
            summary.total_reasoning_tokens += turn.reasoning_tokens
            summary.total_cost_usd += turn.cost_usd
            summary.total_duration_ms += turn.duration_ms

            model = turn.model or "unknown"
            if model not in by_model:
                by_model[model] = {
                    "turns": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cached_tokens": 0,
                    "cost_usd": 0.0,
                }
            by_model[model]["turns"] += 1
            by_model[model]["input_tokens"] += turn.input_tokens
            by_model[model]["output_tokens"] += turn.output_tokens
            by_model[model]["cached_tokens"] += turn.cached_tokens
            by_model[model]["cost_usd"] += turn.cost_usd

        summary.by_model = by_model
        return summary

    def get_last_turn(self) -> TurnUsage | None:
        """Get the most recent turn usage."""
        return self._turns[-1] if self._turns else None

    def format_cost(self, cost_usd: float) -> str:
        """Format cost for display."""
        if cost_usd < 0.01:
            return f"${cost_usd:.4f}"
        return f"${cost_usd:.2f}"

    def format_tokens(self, count: int) -> str:
        """Format token count for display."""
        if count >= 1_000_000:
            return f"{count / 1_000_000:.1f}M"
        if count >= 1_000:
            return f"{count / 1_000:.1f}k"
        return str(count)

    def get_status_display(self) -> str:
        """Get a compact status line display."""
        summary = self.get_session_summary()
        tokens = self.format_tokens(summary.total_tokens)
        cost = self.format_cost(summary.total_cost_usd)
        return f"{tokens} tokens | {cost}"

    def reset(self) -> None:
        """Reset all tracked usage data."""
        self._turns.clear()

    def to_json(self) -> str:
        """Serialize all tracked data to JSON."""
        return json.dumps(
            {
                "turns": [t.to_dict() for t in self._turns],
                "summary": self.get_session_summary().to_dict(),
            },
            indent=2,
        )
