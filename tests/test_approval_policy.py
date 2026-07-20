"""Tests for approval policy engine in danger.py."""

from __future__ import annotations

from agent_terminal_ui.danger import (
    ApprovalEngine,
    ApprovalPolicy,
    DangerLevel,
)


class TestApprovalPolicy:
    def test_enum_values(self) -> None:
        assert ApprovalPolicy.ON_REQUEST.value == "on-request"
        assert ApprovalPolicy.AUTO.value == "auto"
        assert ApprovalPolicy.NEVER.value == "never"


class TestApprovalEngine:
    def test_auto_approves_all(self) -> None:
        engine = ApprovalEngine(policy=ApprovalPolicy.AUTO)
        assert engine.requires_approval("rm -rf /") is False

    def test_never_blocks_all(self) -> None:
        engine = ApprovalEngine(policy=ApprovalPolicy.NEVER)
        assert engine.requires_approval("ls") is True
        assert engine.requires_approval("echo hello") is True

    def test_on_request_safe_approved(self) -> None:
        engine = ApprovalEngine(policy=ApprovalPolicy.ON_REQUEST)
        assert engine.requires_approval("ls -la") is False
        assert engine.requires_approval("cat file.txt") is False

    def test_on_request_dangerous_requires_approval(self) -> None:
        engine = ApprovalEngine(policy=ApprovalPolicy.ON_REQUEST)
        assert engine.requires_approval("rm -rf /tmp/data") is True
        assert engine.requires_approval("docker pull nginx") is True

    def test_auto_allow_prefix(self) -> None:
        engine = ApprovalEngine(
            policy=ApprovalPolicy.ON_REQUEST,
            auto_allow=["cargo check", "npm run"],
        )
        assert engine.requires_approval("cargo check") is False
        assert engine.requires_approval("cargo check --locked") is False
        assert engine.requires_approval("npm run test") is False
        # Not in auto_allow
        assert engine.requires_approval("cargo install something") is True

    def test_add_remove_auto_allow(self) -> None:
        engine = ApprovalEngine()
        engine.add_auto_allow("git status")
        assert engine.check_auto_allow("git status -s") is True
        engine.remove_auto_allow("git status")
        assert engine.check_auto_allow("git status -s") is False

    def test_duplicate_add(self) -> None:
        engine = ApprovalEngine()
        engine.add_auto_allow("git status")
        engine.add_auto_allow("git status")
        assert len(engine.auto_allow) == 1

    def test_plan_mode_stricter(self) -> None:
        engine = ApprovalEngine(policy=ApprovalPolicy.ON_REQUEST)
        # Unknown commands in plan mode require approval
        assert engine.requires_approval("my-custom-tool run", mode="plan") is True
        # But safe commands still pass
        assert engine.requires_approval("cat file.txt", mode="plan") is False

    def test_evaluate_safe(self) -> None:
        engine = ApprovalEngine()
        needs, danger, reason = engine.evaluate("ls -la")
        assert needs is False
        assert danger == DangerLevel.SAFE
        assert "safe" in reason.lower()

    def test_evaluate_dangerous(self) -> None:
        engine = ApprovalEngine()
        needs, danger, reason = engine.evaluate("rm -rf /tmp/data")
        assert needs is True
        assert danger in (DangerLevel.DANGEROUS, DangerLevel.DESTRUCTIVE)

    def test_evaluate_auto_policy(self) -> None:
        engine = ApprovalEngine(policy=ApprovalPolicy.AUTO)
        needs, danger, reason = engine.evaluate("rm -rf /")
        assert needs is False
        assert "auto" in reason.lower()

    def test_evaluate_never_policy(self) -> None:
        engine = ApprovalEngine(policy=ApprovalPolicy.NEVER)
        needs, danger, reason = engine.evaluate("echo hello")
        assert needs is True
        assert "never" in reason.lower()

    def test_evaluate_auto_allow(self) -> None:
        engine = ApprovalEngine(auto_allow=["docker compose"])
        needs, danger, reason = engine.evaluate("docker compose up -d")
        assert needs is False
        assert "auto-allow" in reason.lower()

    def test_policy_setter(self) -> None:
        engine = ApprovalEngine()
        assert engine.policy == ApprovalPolicy.ON_REQUEST
        engine.policy = ApprovalPolicy.AUTO
        assert engine.policy == ApprovalPolicy.AUTO
