"""Multi-tier context compaction engine.

Provides automatic and manual context compaction with configurable
thresholds modeled after DeepSeek-TUI's L1/L2/L3/Cycle system.

Concept: TUI-4 (Context Compaction)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class CompactionTier(Enum):
    """Compaction urgency tiers based on context window pressure."""

    NONE = "none"
    L1 = "l1"  # Light summarization
    L2 = "l2"  # Aggressive summarization
    L3 = "l3"  # Drop old turns
    CYCLE = "cycle"  # Hard reset with summary carry-forward


@dataclass
class CompactionThresholds:
    """Configurable thresholds for auto-compaction triggers."""

    l1_threshold: int = 192_000
    l2_threshold: int = 384_000
    l3_threshold: int = 576_000
    cycle_threshold: int = 768_000
    verbatim_window_turns: int = 16

    def tier_for_tokens(self, token_count: int) -> CompactionTier:
        """Determine the compaction tier for a given token count.

        Args:
            token_count: Current context window token count.

        Returns:
            The appropriate compaction tier.
        """
        if token_count >= self.cycle_threshold:
            return CompactionTier.CYCLE
        if token_count >= self.l3_threshold:
            return CompactionTier.L3
        if token_count >= self.l2_threshold:
            return CompactionTier.L2
        if token_count >= self.l1_threshold:
            return CompactionTier.L1
        return CompactionTier.NONE


@dataclass
class CompactionResult:
    """Result of a compaction operation."""

    tier: CompactionTier
    tokens_before: int
    tokens_after: int
    turns_removed: int = 0
    summary: str = ""
    timestamp: float = field(default_factory=time.time)

    @property
    def tokens_saved(self) -> int:
        return self.tokens_before - self.tokens_after

    @property
    def reduction_pct(self) -> float:
        if self.tokens_before == 0:
            return 0.0
        return (self.tokens_saved / self.tokens_before) * 100

    def to_dict(self) -> dict[str, Any]:
        return {
            "tier": self.tier.value,
            "tokens_before": self.tokens_before,
            "tokens_after": self.tokens_after,
            "tokens_saved": self.tokens_saved,
            "reduction_pct": round(self.reduction_pct, 1),
            "turns_removed": self.turns_removed,
            "summary": self.summary,
        }


class ContextCompactionEngine:
    """Multi-tier context compaction engine.

    Estimates token usage and applies compaction strategies when the
    context window approaches configured thresholds. Supports both
    automatic (triggered on each turn) and manual compaction.
    """

    # Rough estimate: 1 token ~ 4 characters for English text
    CHARS_PER_TOKEN = 4

    def __init__(
        self,
        thresholds: CompactionThresholds | None = None,
        auto_compact: bool = False,
    ) -> None:
        """Initialize the compaction engine.

        Args:
            thresholds: Compaction threshold configuration.
            auto_compact: Whether auto-compaction is enabled.
        """
        self._thresholds = thresholds or CompactionThresholds()
        self._auto_compact = auto_compact
        self._history: list[CompactionResult] = []
        self._total_tokens_saved: int = 0

    @property
    def auto_compact(self) -> bool:
        return self._auto_compact

    @auto_compact.setter
    def auto_compact(self, enabled: bool) -> None:
        self._auto_compact = enabled

    @property
    def thresholds(self) -> CompactionThresholds:
        return self._thresholds

    @property
    def history(self) -> list[CompactionResult]:
        return self._history

    @property
    def total_tokens_saved(self) -> int:
        return self._total_tokens_saved

    def estimate_tokens(self, text: str) -> int:
        """Estimate the token count for a text string.

        Args:
            text: The text to estimate tokens for.

        Returns:
            Estimated token count.
        """
        return max(1, len(text) // self.CHARS_PER_TOKEN)

    def estimate_context_tokens(self, turns: list[dict[str, Any]]) -> int:
        """Estimate total tokens across all turns.

        Args:
            turns: List of turn dictionaries with 'content' fields.

        Returns:
            Estimated total token count.
        """
        total = 0
        for turn in turns:
            content = turn.get("content", "")
            if isinstance(content, str):
                total += self.estimate_tokens(content)
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, str):
                        total += self.estimate_tokens(part)
                    elif isinstance(part, dict):
                        total += self.estimate_tokens(part.get("text", ""))
        return total

    def check_pressure(self, token_count: int) -> CompactionTier:
        """Check context pressure and return the recommended tier.

        Args:
            token_count: Current estimated token count.

        Returns:
            The recommended compaction tier.
        """
        return self._thresholds.tier_for_tokens(token_count)

    def compact(
        self,
        turns: list[dict[str, Any]],
        force_tier: CompactionTier | None = None,
    ) -> tuple[list[dict[str, Any]], CompactionResult]:
        """Apply compaction to a list of turns.

        Args:
            turns: The conversation turns to compact.
            force_tier: Force a specific compaction tier (for manual compaction).

        Returns:
            Tuple of (compacted turns, compaction result).
        """
        tokens_before = self.estimate_context_tokens(turns)
        tier = force_tier or self._thresholds.tier_for_tokens(tokens_before)

        if tier == CompactionTier.NONE:
            result = CompactionResult(
                tier=tier, tokens_before=tokens_before, tokens_after=tokens_before
            )
            return turns, result

        verbatim_window = self._thresholds.verbatim_window_turns
        compacted_turns = list(turns)  # Work on a copy
        turns_removed = 0

        if tier == CompactionTier.L1:
            # Light: summarize old tool call results
            compacted_turns, turns_removed = self._compact_tool_results(
                compacted_turns, verbatim_window
            )
        elif tier == CompactionTier.L2:
            # Aggressive: summarize all turns outside verbatim window
            compacted_turns, turns_removed = self._compact_old_turns(
                compacted_turns, verbatim_window
            )
        elif tier == CompactionTier.L3:
            # Drop: remove old turns entirely, keep summary
            compacted_turns, turns_removed = self._drop_old_turns(
                compacted_turns, verbatim_window
            )
        elif tier == CompactionTier.CYCLE:
            # Hard reset: keep only a summary and recent turns
            compacted_turns, turns_removed = self._cycle_reset(
                compacted_turns, max(4, verbatim_window // 4)
            )

        tokens_after = self.estimate_context_tokens(compacted_turns)
        result = CompactionResult(
            tier=tier,
            tokens_before=tokens_before,
            tokens_after=tokens_after,
            turns_removed=turns_removed,
            summary=f"{tier.value} compaction: {tokens_before - tokens_after} "
            "tokens saved",
        )

        self._history.append(result)
        self._total_tokens_saved += result.tokens_saved
        return compacted_turns, result

    def _compact_tool_results(
        self, turns: list[dict[str, Any]], verbatim_window: int
    ) -> tuple[list[dict[str, Any]], int]:
        """Summarize tool call results in older turns."""
        removed = 0
        cutoff = max(0, len(turns) - verbatim_window)

        for i in range(cutoff):
            turn = turns[i]
            content = turn.get("content", "")
            if isinstance(content, str) and len(content) > 500:
                # Truncate long tool results
                turns[i] = {**turn, "content": content[:200] + "\n[... compacted ...]"}
                removed += 1

        return turns, removed

    def _compact_old_turns(
        self, turns: list[dict[str, Any]], verbatim_window: int
    ) -> tuple[list[dict[str, Any]], int]:
        """Aggressively summarize turns outside the verbatim window."""
        if len(turns) <= verbatim_window:
            return turns, 0

        cutoff = len(turns) - verbatim_window
        old_turns = turns[:cutoff]
        recent_turns = turns[cutoff:]

        # Create a summary of old turns
        summary_parts = []
        for turn in old_turns:
            role = turn.get("role", "unknown")
            content = turn.get("content", "")
            if isinstance(content, str) and content.strip():
                truncated = content[:100].replace("\n", " ")
                summary_parts.append(f"[{role}] {truncated}...")

        summary_content = "Previous conversation summary:\n" + "\n".join(
            summary_parts[-10:]
        )
        summary_turn = {"role": "system", "content": summary_content}

        return [summary_turn] + recent_turns, len(old_turns)

    def _drop_old_turns(
        self, turns: list[dict[str, Any]], verbatim_window: int
    ) -> tuple[list[dict[str, Any]], int]:
        """Drop old turns, keeping only a compact summary."""
        if len(turns) <= verbatim_window:
            return turns, 0

        cutoff = len(turns) - verbatim_window
        recent_turns = turns[cutoff:]
        summary = {
            "role": "system",
            "content": f"[{cutoff} earlier turns dropped for context management]",
        }
        return [summary] + recent_turns, cutoff

    def _cycle_reset(
        self, turns: list[dict[str, Any]], keep_count: int
    ) -> tuple[list[dict[str, Any]], int]:
        """Hard cycle reset: keep only the most recent turns."""
        if len(turns) <= keep_count:
            return turns, 0

        dropped = len(turns) - keep_count
        recent = turns[-keep_count:]
        summary = {
            "role": "system",
            "content": f"[Context cycled: {dropped} turns archived. "
            "Starting fresh with summary carry-forward.]",
        }
        return [summary] + recent, dropped

    def get_status(self, current_tokens: int) -> dict[str, Any]:
        """Get compaction status for display.

        Args:
            current_tokens: Current token count.

        Returns:
            Status dictionary.
        """
        tier = self.check_pressure(current_tokens)
        return {
            "current_tokens": current_tokens,
            "pressure_tier": tier.value,
            "auto_compact": self._auto_compact,
            "total_compactions": len(self._history),
            "total_tokens_saved": self._total_tokens_saved,
            "thresholds": {
                "l1": self._thresholds.l1_threshold,
                "l2": self._thresholds.l2_threshold,
                "l3": self._thresholds.l3_threshold,
                "cycle": self._thresholds.cycle_threshold,
            },
        }
