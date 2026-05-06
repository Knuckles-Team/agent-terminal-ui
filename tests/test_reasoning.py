"""Tests for reasoning.py -- Reasoning effort tiers and auto model routing."""

from __future__ import annotations

import pytest

from agent_terminal_ui.reasoning import (
    AutoModelRouter,
    AutoRouteDecision,
    ReasoningEffortManager,
    ReasoningEffortTier,
)


class TestReasoningEffortTier:
    def test_tier_values(self) -> None:
        assert ReasoningEffortTier.OFF.value == "off"
        assert ReasoningEffortTier.HIGH.value == "high"
        assert ReasoningEffortTier.MAX.value == "max"

    def test_cycle(self) -> None:
        assert ReasoningEffortTier.OFF.next() == ReasoningEffortTier.HIGH
        assert ReasoningEffortTier.HIGH.next() == ReasoningEffortTier.MAX
        assert ReasoningEffortTier.MAX.next() == ReasoningEffortTier.OFF

    def test_display_icon(self) -> None:
        assert ReasoningEffortTier.OFF.display_icon == ""
        assert ReasoningEffortTier.HIGH.display_icon == "⚡"
        assert ReasoningEffortTier.MAX.display_icon == "⚡⚡"

    def test_display_label(self) -> None:
        assert "Off" in ReasoningEffortTier.OFF.display_label
        assert "High" in ReasoningEffortTier.HIGH.display_label
        assert "Max" in ReasoningEffortTier.MAX.display_label


class TestAutoRouteDecision:
    def test_to_dict(self) -> None:
        decision = AutoRouteDecision("pro", ReasoningEffortTier.HIGH, "test")
        d = decision.to_dict()
        assert d["model"] == "pro"
        assert d["reasoning_effort"] == "high"
        assert d["rationale"] == "test"


class TestAutoModelRouter:
    def test_plan_mode_uses_pro(self) -> None:
        router = AutoModelRouter()
        decision = router.route("anything", mode="plan")
        assert decision.model == "pro"
        assert decision.reasoning_effort == ReasoningEffortTier.HIGH

    def test_code_mode_uses_pro(self) -> None:
        router = AutoModelRouter()
        decision = router.route("anything", mode="code")
        assert decision.model == "pro"

    def test_complex_long_query_uses_max(self) -> None:
        router = AutoModelRouter()
        query = "Please debug this complex issue " + "x" * 100
        decision = router.route(query)
        assert decision.reasoning_effort == ReasoningEffortTier.MAX

    def test_complex_short_query_uses_high(self) -> None:
        router = AutoModelRouter()
        decision = router.route("fix the bug")
        assert decision.reasoning_effort == ReasoningEffortTier.HIGH

    def test_simple_short_query_uses_off(self) -> None:
        router = AutoModelRouter()
        decision = router.route("explain this")
        assert decision.model == "flash"
        assert decision.reasoning_effort == ReasoningEffortTier.OFF

    def test_extended_conversation(self) -> None:
        router = AutoModelRouter()
        decision = router.route("continue", context_turns=15)
        assert decision.reasoning_effort == ReasoningEffortTier.HIGH

    def test_default_balanced(self) -> None:
        router = AutoModelRouter()
        decision = router.route("do something medium length here please")
        assert decision.model == "default"


class TestReasoningEffortManager:
    def test_initial_tier(self) -> None:
        mgr = ReasoningEffortManager()
        assert mgr.current_tier == ReasoningEffortTier.HIGH

    def test_cycle(self) -> None:
        mgr = ReasoningEffortManager()
        assert mgr.cycle() == ReasoningEffortTier.MAX
        assert mgr.cycle() == ReasoningEffortTier.OFF
        assert mgr.cycle() == ReasoningEffortTier.HIGH

    def test_set_tier(self) -> None:
        mgr = ReasoningEffortManager()
        mgr.current_tier = ReasoningEffortTier.MAX
        assert mgr.current_tier == ReasoningEffortTier.MAX

    def test_auto_mode_toggle(self) -> None:
        mgr = ReasoningEffortManager()
        assert mgr.auto_mode is False
        mgr.auto_mode = True
        assert mgr.auto_mode is True

    def test_route_query_manual(self) -> None:
        mgr = ReasoningEffortManager(initial_tier=ReasoningEffortTier.MAX)
        decision = mgr.route_query("anything")
        assert decision.reasoning_effort == ReasoningEffortTier.MAX
        assert decision.rationale == "Manual reasoning effort setting"

    def test_route_query_auto(self) -> None:
        mgr = ReasoningEffortManager(auto_mode=True)
        decision = mgr.route_query("explain this")
        assert decision.model == "flash"

    def test_status_display_auto(self) -> None:
        mgr = ReasoningEffortManager(auto_mode=True)
        assert "Auto" in mgr.get_status_display()

    def test_status_display_off(self) -> None:
        mgr = ReasoningEffortManager(initial_tier=ReasoningEffortTier.OFF)
        assert "Off" in mgr.get_status_display()

    def test_status_display_max(self) -> None:
        mgr = ReasoningEffortManager(initial_tier=ReasoningEffortTier.MAX)
        assert "Max" in mgr.get_status_display()
