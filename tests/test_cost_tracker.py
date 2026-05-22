"""Tests for cost_tracker.py -- Per-turn cost and token tracking."""

from __future__ import annotations

import json

import pytest

from agent_terminal_ui.cost_tracker import CostTracker, SessionUsageSummary, TurnUsage


class TestTurnUsage:
    def test_total_tokens(self) -> None:
        usage = TurnUsage(input_tokens=100, output_tokens=50)
        assert usage.total_tokens == 150

    def test_cache_hit_rate(self) -> None:
        usage = TurnUsage(input_tokens=100, cached_tokens=40)
        assert usage.cache_hit_rate == 0.4

    def test_cache_hit_rate_zero(self) -> None:
        usage = TurnUsage(input_tokens=0)
        assert usage.cache_hit_rate == 0.0

    def test_to_dict(self) -> None:
        usage = TurnUsage(
            turn_number=1, model="gpt-4o", input_tokens=100, output_tokens=50
        )
        d = usage.to_dict()
        assert d["turn_number"] == 1
        assert d["model"] == "gpt-4o"
        assert d["total_tokens"] == 150


class TestCostTracker:
    def test_compute_cost_default(self) -> None:
        tracker = CostTracker()
        cost = tracker.compute_cost(
            "default", input_tokens=1_000_000, output_tokens=500_000
        )
        assert cost > 0

    def test_compute_cost_with_cache(self) -> None:
        tracker = CostTracker()
        cost_no_cache = tracker.compute_cost("default", 1000, 500)
        cost_cached = tracker.compute_cost("default", 1000, 500, cached_tokens=500)
        assert cost_cached < cost_no_cache

    def test_compute_cost_unknown_model(self) -> None:
        tracker = CostTracker()
        cost = tracker.compute_cost("unknown-model-xyz", 1000, 500)
        # Falls back to "default" pricing
        assert cost > 0

    def test_record_turn(self) -> None:
        tracker = CostTracker()
        usage = tracker.record_turn(
            1,
            "pro",
            1000,
            500,
            cached_tokens=200,
            reasoning_tokens=100,
            duration_ms=5000,
        )
        assert usage.turn_number == 1
        assert usage.cost_usd > 0
        assert len(tracker.turns) == 1

    def test_session_summary(self) -> None:
        tracker = CostTracker()
        tracker.record_turn(1, "pro", 1000, 500)
        tracker.record_turn(2, "flash", 2000, 300)
        tracker.record_turn(3, "pro", 500, 200)

        summary = tracker.get_session_summary()
        assert summary.total_turns == 3
        assert summary.total_input_tokens == 3500
        assert summary.total_output_tokens == 1000
        assert summary.total_cost_usd > 0
        assert "pro" in summary.by_model
        assert "flash" in summary.by_model
        assert summary.by_model["pro"]["turns"] == 2

    def test_session_summary_to_dict(self) -> None:
        tracker = CostTracker()
        tracker.record_turn(1, "pro", 1000, 500)
        d = tracker.get_session_summary().to_dict()
        assert "total_turns" in d
        assert "by_model" in d

    def test_get_last_turn(self) -> None:
        tracker = CostTracker()
        assert tracker.get_last_turn() is None
        tracker.record_turn(1, "pro", 100, 50)
        tracker.record_turn(2, "flash", 200, 100)
        last = tracker.get_last_turn()
        assert last is not None
        assert last.turn_number == 2

    def test_set_pricing(self) -> None:
        tracker = CostTracker()
        tracker.set_pricing("custom-model", 1.0, 2.0, 0.5)
        cost = tracker.compute_cost("custom-model", 1_000_000, 1_000_000)
        assert cost == pytest.approx(3.0, abs=0.01)

    def test_format_cost(self) -> None:
        tracker = CostTracker()
        assert tracker.format_cost(0.001) == "$0.0010"
        assert tracker.format_cost(1.50) == "$1.50"

    def test_format_tokens(self) -> None:
        tracker = CostTracker()
        assert tracker.format_tokens(500) == "500"
        assert tracker.format_tokens(1500) == "1.5k"
        assert tracker.format_tokens(1_500_000) == "1.5M"

    def test_status_display(self) -> None:
        tracker = CostTracker()
        tracker.record_turn(1, "pro", 1000, 500)
        display = tracker.get_status_display()
        assert "tokens" in display
        assert "$" in display

    def test_reset(self) -> None:
        tracker = CostTracker()
        tracker.record_turn(1, "pro", 100, 50)
        tracker.reset()
        assert len(tracker.turns) == 0

    def test_to_json(self) -> None:
        tracker = CostTracker()
        tracker.record_turn(1, "pro", 100, 50)
        data = json.loads(tracker.to_json())
        assert "turns" in data
        assert "summary" in data
        assert len(data["turns"]) == 1


class TestSessionUsageSummary:
    def test_total_tokens(self) -> None:
        s = SessionUsageSummary(total_input_tokens=100, total_output_tokens=50)
        assert s.total_tokens == 150

    def test_avg_cache_hit_rate(self) -> None:
        s = SessionUsageSummary(total_input_tokens=100, total_cached_tokens=30)
        assert s.avg_cache_hit_rate == 0.3

    def test_avg_cache_hit_rate_zero(self) -> None:
        s = SessionUsageSummary()
        assert s.avg_cache_hit_rate == 0.0
