"""Tests for workspace_snapshots.py -- Side-git workspace snapshots."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agent_terminal_ui.workspace_snapshots import (
    SnapshotRecord,
    WorkspaceSnapshotManager,
)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "project"
    ws.mkdir()
    (ws / "main.py").write_text("print('hello')\n")
    return ws


@pytest.fixture
def snapshot_base(tmp_path: Path) -> Path:
    return tmp_path / "snapshots"


class TestSnapshotRecord:
    def test_to_dict(self) -> None:
        record = SnapshotRecord(
            tag="pre-turn-1", turn_number=1, phase="pre", workspace="/project"
        )
        d = record.to_dict()
        assert d["tag"] == "pre-turn-1"
        assert d["turn_number"] == 1
        assert d["phase"] == "pre"

    def test_fields(self) -> None:
        record = SnapshotRecord(
            tag="post-turn-5", turn_number=5, phase="post", commit_hash="abc123"
        )
        assert record.commit_hash == "abc123"


class TestWorkspaceSnapshotManager:
    def test_init(self, workspace: Path, snapshot_base: Path) -> None:
        mgr = WorkspaceSnapshotManager(workspace, snapshot_base)
        assert mgr.workspace == workspace.resolve()
        assert mgr.snapshot_dir.parent == snapshot_base

    def test_initialize_creates_git(self, workspace: Path, snapshot_base: Path) -> None:
        mgr = WorkspaceSnapshotManager(workspace, snapshot_base)
        mgr.initialize()
        # Should have created a .git dir
        assert mgr.snapshot_dir.exists()
        git_dir = mgr.snapshot_dir / ".git"
        assert git_dir.exists()

    def test_pre_turn_snapshot(self, workspace: Path, snapshot_base: Path) -> None:
        mgr = WorkspaceSnapshotManager(workspace, snapshot_base)
        record = mgr.pre_turn_snapshot(1)
        assert record is not None
        assert record.tag == "pre-turn-1"
        assert record.phase == "pre"
        assert record.commit_hash

    def test_post_turn_snapshot(self, workspace: Path, snapshot_base: Path) -> None:
        mgr = WorkspaceSnapshotManager(workspace, snapshot_base)
        record = mgr.post_turn_snapshot(1)
        assert record is not None
        assert record.tag == "post-turn-1"
        assert record.phase == "post"

    def test_multiple_snapshots(self, workspace: Path, snapshot_base: Path) -> None:
        mgr = WorkspaceSnapshotManager(workspace, snapshot_base)
        mgr.pre_turn_snapshot(1)
        (workspace / "new_file.py").write_text("x = 1\n")
        mgr.post_turn_snapshot(1)
        mgr.pre_turn_snapshot(2)

        snapshots = mgr.list_snapshots()
        assert len(snapshots) >= 3

    def test_restore(self, workspace: Path, snapshot_base: Path) -> None:
        mgr = WorkspaceSnapshotManager(workspace, snapshot_base)
        mgr.pre_turn_snapshot(1)

        # Make a change
        (workspace / "main.py").write_text("print('changed')\n")
        mgr.post_turn_snapshot(1)

        # Restore to pre-turn
        assert mgr.restore(1, "pre") is True
        content = (workspace / "main.py").read_text()
        assert content == "print('hello')\n"

    def test_restore_nonexistent(self, workspace: Path, snapshot_base: Path) -> None:
        mgr = WorkspaceSnapshotManager(workspace, snapshot_base)
        mgr.initialize()
        assert mgr.restore(999) is False

    def test_get_diff(self, workspace: Path, snapshot_base: Path) -> None:
        mgr = WorkspaceSnapshotManager(workspace, snapshot_base)
        mgr.pre_turn_snapshot(1)
        (workspace / "new.txt").write_text("new content\n")
        mgr.post_turn_snapshot(1)

        diff = mgr.get_diff(1, 1)
        assert "new.txt" in diff or "new content" in diff

    def test_list_snapshots_empty(self, workspace: Path, snapshot_base: Path) -> None:
        mgr = WorkspaceSnapshotManager(workspace, snapshot_base)
        mgr.initialize()
        snapshots = mgr.list_snapshots()
        # Only initial commit tag-less
        assert isinstance(snapshots, list)

    def test_snapshot_failure_returns_none(
        self, workspace: Path, snapshot_base: Path
    ) -> None:
        mgr = WorkspaceSnapshotManager(workspace, snapshot_base)
        with patch.object(
            mgr, "_run_git", side_effect=subprocess.CalledProcessError(1, "git")
        ):
            mgr._initialized = True
            result = mgr._take_snapshot(1, "pre")
            assert result is None

    def test_deterministic_hash(self, workspace: Path, snapshot_base: Path) -> None:
        mgr1 = WorkspaceSnapshotManager(workspace, snapshot_base)
        mgr2 = WorkspaceSnapshotManager(workspace, snapshot_base)
        assert mgr1.snapshot_dir == mgr2.snapshot_dir

    def test_different_workspace_different_dir(
        self, tmp_path: Path, snapshot_base: Path
    ) -> None:
        ws1 = tmp_path / "project1"
        ws1.mkdir()
        ws2 = tmp_path / "project2"
        ws2.mkdir()
        mgr1 = WorkspaceSnapshotManager(ws1, snapshot_base)
        mgr2 = WorkspaceSnapshotManager(ws2, snapshot_base)
        assert mgr1.snapshot_dir != mgr2.snapshot_dir
