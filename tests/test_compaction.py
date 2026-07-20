"""Tests for compaction.py -- Context compaction engine."""

from __future__ import annotations

from agent_terminal_ui.compaction import (
    CompactionResult,
    CompactionThresholds,
    CompactionTier,
    ContextCompactionEngine,
)


class TestCompactionThresholds:
    def test_tier_none(self) -> None:
        t = CompactionThresholds()
        assert t.tier_for_tokens(100_000) == CompactionTier.NONE

    def test_tier_l1(self) -> None:
        t = CompactionThresholds()
        assert t.tier_for_tokens(200_000) == CompactionTier.L1

    def test_tier_l2(self) -> None:
        t = CompactionThresholds()
        assert t.tier_for_tokens(400_000) == CompactionTier.L2

    def test_tier_l3(self) -> None:
        t = CompactionThresholds()
        assert t.tier_for_tokens(600_000) == CompactionTier.L3

    def test_tier_cycle(self) -> None:
        t = CompactionThresholds()
        assert t.tier_for_tokens(800_000) == CompactionTier.CYCLE

    def test_exact_boundaries(self) -> None:
        t = CompactionThresholds()
        assert t.tier_for_tokens(191_999) == CompactionTier.NONE
        assert t.tier_for_tokens(192_000) == CompactionTier.L1
        assert t.tier_for_tokens(384_000) == CompactionTier.L2


class TestCompactionResult:
    def test_tokens_saved(self) -> None:
        r = CompactionResult(
            tier=CompactionTier.L1, tokens_before=1000, tokens_after=700
        )
        assert r.tokens_saved == 300

    def test_reduction_pct(self) -> None:
        r = CompactionResult(
            tier=CompactionTier.L1, tokens_before=1000, tokens_after=500
        )
        assert r.reduction_pct == 50.0

    def test_zero_before(self) -> None:
        r = CompactionResult(tier=CompactionTier.NONE, tokens_before=0, tokens_after=0)
        assert r.reduction_pct == 0.0

    def test_to_dict(self) -> None:
        r = CompactionResult(
            tier=CompactionTier.L2,
            tokens_before=2000,
            tokens_after=1000,
            turns_removed=5,
        )
        d = r.to_dict()
        assert d["tier"] == "l2"
        assert d["tokens_saved"] == 1000
        assert d["turns_removed"] == 5


class TestContextCompactionEngine:
    def test_estimate_tokens(self) -> None:
        engine = ContextCompactionEngine()
        tokens = engine.estimate_tokens("hello world")
        assert tokens >= 1

    def test_estimate_context_tokens(self) -> None:
        engine = ContextCompactionEngine()
        turns = [
            {"role": "user", "content": "Hello " * 100},
            {"role": "assistant", "content": "World " * 200},
        ]
        total = engine.estimate_context_tokens(turns)
        assert total > 0

    def test_compact_no_pressure(self) -> None:
        engine = ContextCompactionEngine()
        turns = [{"role": "user", "content": "Short message"}]
        compacted, result = engine.compact(turns)
        assert result.tier == CompactionTier.NONE
        assert len(compacted) == 1

    def test_compact_l1_truncates_long_content(self) -> None:
        engine = ContextCompactionEngine()
        turns = [{"role": "user", "content": "x" * 2000}] * 20
        compacted, result = engine.compact(turns, force_tier=CompactionTier.L1)
        assert result.tier == CompactionTier.L1
        assert result.tokens_before > result.tokens_after

    def test_compact_l2_summarizes(self) -> None:
        engine = ContextCompactionEngine()
        turns = [{"role": "user", "content": f"message {i}"} for i in range(20)]
        compacted, result = engine.compact(turns, force_tier=CompactionTier.L2)
        assert result.tier == CompactionTier.L2
        assert result.turns_removed > 0
        # Should have a summary turn + recent turns
        assert any(
            "summary" in str(t.get("content", "")).lower() or t.get("role") == "system"
            for t in compacted
        )

    def test_compact_l3_drops(self) -> None:
        engine = ContextCompactionEngine()
        turns = [{"role": "user", "content": f"msg {i}"} for i in range(20)]
        compacted, result = engine.compact(turns, force_tier=CompactionTier.L3)
        assert result.turns_removed > 0
        assert len(compacted) < len(turns)

    def test_compact_cycle_hard_reset(self) -> None:
        engine = ContextCompactionEngine()
        turns = [{"role": "user", "content": f"msg {i}"} for i in range(50)]
        compacted, result = engine.compact(turns, force_tier=CompactionTier.CYCLE)
        assert result.turns_removed > 0
        assert len(compacted) <= 17  # keep_count = max(4, 16//4) = 4, + 1 summary

    def test_auto_compact_disabled(self) -> None:
        engine = ContextCompactionEngine(auto_compact=False)
        assert engine.auto_compact is False

    def test_auto_compact_enabled(self) -> None:
        engine = ContextCompactionEngine(auto_compact=True)
        assert engine.auto_compact is True
        engine.auto_compact = False
        assert engine.auto_compact is False

    def test_history_tracking(self) -> None:
        engine = ContextCompactionEngine()
        turns = [{"role": "user", "content": "x" * 2000}] * 20
        engine.compact(turns, force_tier=CompactionTier.L1)
        engine.compact(turns, force_tier=CompactionTier.L2)
        assert len(engine.history) == 2
        assert engine.total_tokens_saved > 0

    def test_get_status(self) -> None:
        engine = ContextCompactionEngine()
        status = engine.get_status(100_000)
        assert status["pressure_tier"] == "none"
        assert "thresholds" in status

    def test_check_pressure(self) -> None:
        engine = ContextCompactionEngine()
        assert engine.check_pressure(100_000) == CompactionTier.NONE
        assert engine.check_pressure(500_000) == CompactionTier.L2
