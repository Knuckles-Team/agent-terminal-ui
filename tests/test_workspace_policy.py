"""Tests for workspace_policy.py -- Workspace boundary enforcement."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_terminal_ui.workspace_policy import (
    FileOperation,
    PolicyViolation,
    SandboxMode,
    WorkspacePolicy,
)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "project"
    ws.mkdir()
    return ws


class TestSandboxMode:
    def test_enum_values(self) -> None:
        assert SandboxMode.READ_ONLY.value == "read-only"
        assert SandboxMode.WORKSPACE_WRITE.value == "workspace-write"
        assert SandboxMode.DANGER_FULL_ACCESS.value == "danger-full-access"


class TestWorkspacePolicy:
    def test_read_always_allowed(self, workspace: Path) -> None:
        policy = WorkspacePolicy(workspace, SandboxMode.READ_ONLY)
        result = policy.check_operation(FileOperation.READ, workspace / "file.py")
        assert result is None

    def test_read_only_blocks_writes(self, workspace: Path) -> None:
        policy = WorkspacePolicy(workspace, SandboxMode.READ_ONLY)
        result = policy.check_operation(FileOperation.WRITE, workspace / "file.py")
        assert result is not None
        assert isinstance(result, PolicyViolation)

    def test_read_only_blocks_delete(self, workspace: Path) -> None:
        policy = WorkspacePolicy(workspace, SandboxMode.READ_ONLY)
        result = policy.check_operation(FileOperation.DELETE, workspace / "file.py")
        assert result is not None

    def test_workspace_write_allows_inside(self, workspace: Path) -> None:
        policy = WorkspacePolicy(workspace, SandboxMode.WORKSPACE_WRITE)
        result = policy.check_operation(
            FileOperation.WRITE, workspace / "src" / "main.py"
        )
        assert result is None

    def test_workspace_write_blocks_outside(self, workspace: Path) -> None:
        policy = WorkspacePolicy(workspace, SandboxMode.WORKSPACE_WRITE)
        result = policy.check_operation(FileOperation.WRITE, "/etc/passwd")
        assert result is not None

    def test_danger_full_access_allows_all(self, workspace: Path) -> None:
        policy = WorkspacePolicy(workspace, SandboxMode.DANGER_FULL_ACCESS)
        result = policy.check_operation(FileOperation.WRITE, "/etc/hosts")
        assert result is None

    def test_danger_full_access_allows_delete(self, workspace: Path) -> None:
        policy = WorkspacePolicy(workspace, SandboxMode.DANGER_FULL_ACCESS)
        result = policy.check_operation(FileOperation.DELETE, "/tmp/somefile")
        assert result is None

    def test_trust_mode_allows_reads_outside(self, workspace: Path) -> None:
        policy = WorkspacePolicy(
            workspace, SandboxMode.WORKSPACE_WRITE, trust_mode=True
        )
        result = policy.check_operation(FileOperation.READ, "/etc/hosts")
        assert result is None

    def test_explicit_deny_path(self, workspace: Path) -> None:
        policy = WorkspacePolicy(workspace, SandboxMode.DANGER_FULL_ACCESS)
        policy.add_denied_path("/secret")
        result = policy.check_operation(FileOperation.READ, "/secret/key")
        assert result is not None

    def test_explicit_allow_path(self, workspace: Path) -> None:
        policy = WorkspacePolicy(workspace, SandboxMode.WORKSPACE_WRITE)
        policy.add_allowed_path("/tmp/scratch")
        result = policy.check_operation(FileOperation.WRITE, "/tmp/scratch/file.txt")
        assert result is None

    def test_deny_overrides_allow(self, workspace: Path) -> None:
        policy = WorkspacePolicy(workspace, SandboxMode.DANGER_FULL_ACCESS)
        policy.add_allowed_path("/data")
        policy.add_denied_path("/data/sensitive")
        result = policy.check_operation(
            FileOperation.READ, "/data/sensitive/secret.txt"
        )
        assert result is not None

    def test_is_within_workspace(self, workspace: Path) -> None:
        policy = WorkspacePolicy(workspace)
        assert policy.is_within_workspace(workspace / "src" / "main.py") is True
        assert policy.is_within_workspace("/etc/hosts") is False

    def test_sandbox_mode_setter(self, workspace: Path) -> None:
        policy = WorkspacePolicy(workspace)
        policy.sandbox_mode = SandboxMode.READ_ONLY
        assert policy.sandbox_mode == SandboxMode.READ_ONLY

    def test_trust_mode_setter(self, workspace: Path) -> None:
        policy = WorkspacePolicy(workspace)
        policy.trust_mode = True
        assert policy.trust_mode is True

    def test_violations_tracking(self, workspace: Path) -> None:
        policy = WorkspacePolicy(workspace, SandboxMode.READ_ONLY)
        policy.check_operation(FileOperation.WRITE, workspace / "a.py")
        policy.check_operation(FileOperation.DELETE, workspace / "b.py")
        assert len(policy.violations) == 2

    def test_clear_violations(self, workspace: Path) -> None:
        policy = WorkspacePolicy(workspace, SandboxMode.READ_ONLY)
        policy.check_operation(FileOperation.WRITE, workspace / "a.py")
        policy.clear_violations()
        assert len(policy.violations) == 0

    def test_get_status(self, workspace: Path) -> None:
        policy = WorkspacePolicy(
            workspace, SandboxMode.WORKSPACE_WRITE, trust_mode=True
        )
        status = policy.get_status()
        assert status["sandbox_mode"] == "workspace-write"
        assert status["trust_mode"] is True


class TestPolicyViolation:
    def test_str(self) -> None:
        v = PolicyViolation(
            FileOperation.WRITE, "/etc/hosts", SandboxMode.READ_ONLY, "Blocked"
        )
        s = str(v)
        assert "read-only" in s
        assert "write" in s

    def test_to_dict(self) -> None:
        v = PolicyViolation(
            FileOperation.DELETE,
            "/data",
            SandboxMode.WORKSPACE_WRITE,
            "Outside workspace",
        )
        d = v.to_dict()
        assert d["operation"] == "delete"
        assert d["sandbox"] == "workspace-write"
