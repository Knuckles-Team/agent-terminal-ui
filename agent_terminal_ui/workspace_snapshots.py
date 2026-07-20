"""Side-git workspace snapshots for turn-level rollback.

Takes pre/post-turn snapshots using a side git repository, allowing
users to restore workspace state without touching the project's own
``.git``. Modeled after DeepSeek-TUI's workspace snapshot system.

Concept: TUI-2 (Workspace Snapshots)
"""

from __future__ import annotations

import hashlib
import logging
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_SNAPSHOT_DIR = Path.home() / ".config" / "agent-terminal-ui" / "snapshots"
DEFAULT_MAX_AGE_DAYS = 7


@dataclass
class SnapshotRecord:
    """Metadata for a single workspace snapshot."""

    tag: str
    turn_number: int
    phase: str  # "pre" or "post"
    created_at: float = field(default_factory=time.time)
    workspace: str = ""
    commit_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dictionary."""
        return {
            "tag": self.tag,
            "turn_number": self.turn_number,
            "phase": self.phase,
            "created_at": self.created_at,
            "workspace": self.workspace,
            "commit_hash": self.commit_hash,
        }


class WorkspaceSnapshotManager:
    """Manages side-git workspace snapshots for turn-level rollback.

    Each turn produces a pre-turn and post-turn snapshot stored in a
    side git repository at ``~/.config/agent-terminal-ui/snapshots/<hash>/``.
    The user's own ``.git`` is never touched.
    """

    def __init__(
        self,
        workspace: str | Path,
        snapshot_base: Path | None = None,
        max_age_days: int = DEFAULT_MAX_AGE_DAYS,
    ) -> None:
        """Initialize the snapshot manager.

        Args:
            workspace: The workspace directory to snapshot.
            snapshot_base: Base directory for snapshot storage.
            max_age_days: Maximum age for snapshot pruning.
        """
        self._workspace = Path(workspace).resolve()
        self._max_age_days = max_age_days

        # Create a deterministic hash for the workspace path
        workspace_hash = hashlib.sha256(str(self._workspace).encode()).hexdigest()[:12]

        self._snapshot_dir = (snapshot_base or DEFAULT_SNAPSHOT_DIR) / workspace_hash
        self._git_dir = self._snapshot_dir / ".git"
        self._snapshots: list[SnapshotRecord] = []
        self._initialized = False

    @property
    def snapshot_dir(self) -> Path:
        """The snapshot storage directory."""
        return self._snapshot_dir

    @property
    def workspace(self) -> Path:
        """The workspace directory being snapshotted."""
        return self._workspace

    def _run_git(
        self, *args: str, check: bool = True
    ) -> subprocess.CompletedProcess[str]:
        """Run a git command against the side-git repo.

        Args:
            *args: Git command arguments.
            check: Whether to raise on non-zero exit.

        Returns:
            The completed process result.
        """
        git_cmd = shutil.which("git") or "git"
        cmd = [
            git_cmd,
            f"--git-dir={self._git_dir}",
            f"--work-tree={self._workspace}",
            *args,
        ]
        return subprocess.run(  # nosec B603
            cmd,
            capture_output=True,
            text=True,
            check=check,
            timeout=30,
        )

    def initialize(self) -> None:
        """Initialize the side-git repository if needed."""
        if self._initialized:
            return

        self._snapshot_dir.mkdir(parents=True, exist_ok=True)

        if not (self._git_dir / "HEAD").exists():
            # Initialize the git-dir as a bare repo, then configure it
            # to work with our workspace as work-tree via --git-dir/--work-tree flags
            self._git_dir.mkdir(parents=True, exist_ok=True)
            git_cmd = shutil.which("git") or "git"
            subprocess.run(  # nosec B603 B607
                [git_cmd, "init", "--bare", str(self._git_dir)],
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
            )

            # Configure user identity for commits (required in CI / containers)
            self._run_git("config", "user.email", "agent-terminal-ui@local")
            self._run_git("config", "user.name", "Agent Terminal UI")

            # Bare repos need core.bare=false to work with --work-tree
            self._run_git("config", "core.bare", "false")

            # Create initial commit so we have a HEAD
            self._run_git("add", "-A")
            self._run_git(
                "commit",
                "--allow-empty",
                "-m",
                "Initial snapshot repository",
            )

        self._initialized = True
        self._prune_old_snapshots()

    def pre_turn_snapshot(self, turn_number: int) -> SnapshotRecord | None:
        """Take a pre-turn snapshot of the workspace.

        Args:
            turn_number: The turn number about to begin.

        Returns:
            The snapshot record, or None on failure.
        """
        return self._take_snapshot(turn_number, "pre")

    def post_turn_snapshot(self, turn_number: int) -> SnapshotRecord | None:
        """Take a post-turn snapshot of the workspace.

        Args:
            turn_number: The turn number that just completed.

        Returns:
            The snapshot record, or None on failure.
        """
        return self._take_snapshot(turn_number, "post")

    def _take_snapshot(self, turn_number: int, phase: str) -> SnapshotRecord | None:
        """Internal snapshot creation.

        Args:
            turn_number: The turn number.
            phase: Either "pre" or "post".

        Returns:
            The snapshot record, or None on failure.
        """
        try:
            self.initialize()

            tag = f"{phase}-turn-{turn_number}"

            # Stage all changes
            self._run_git("add", "-A")

            # Commit with descriptive message
            self._run_git(
                "commit",
                "--allow-empty",
                "-m",
                f"{phase}-turn {turn_number} snapshot",
                check=False,
            )

            # Get the commit hash
            hash_result = self._run_git("rev-parse", "HEAD")
            commit_hash = hash_result.stdout.strip()

            # Tag the commit
            self._run_git("tag", "-f", tag)

            record = SnapshotRecord(
                tag=tag,
                turn_number=turn_number,
                phase=phase,
                workspace=str(self._workspace),
                commit_hash=commit_hash,
            )
            self._snapshots.append(record)
            logger.info(f"Created snapshot: {tag} ({commit_hash[:8]})")
            return record

        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as e:
            logger.warning(f"Failed to create {phase}-turn snapshot: {e}")
            return None

    def restore(self, turn_number: int, phase: str = "pre") -> bool:
        """Restore the workspace to a specific snapshot.

        Args:
            turn_number: The turn number to restore to.
            phase: Which phase to restore ("pre" or "post").

        Returns:
            True if restoration succeeded.
        """
        try:
            self.initialize()
            tag = f"{phase}-turn-{turn_number}"

            # Check if tag exists
            result = self._run_git("tag", "-l", tag)
            if not result.stdout.strip():
                logger.warning(f"Snapshot tag not found: {tag}")
                return False

            # Checkout the tagged commit into the work tree
            self._run_git("checkout", tag, "--", ".")
            logger.info(f"Restored workspace to snapshot: {tag}")
            return True

        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as e:
            logger.error(f"Failed to restore snapshot {tag}: {e}")
            return False

    def list_snapshots(self) -> list[SnapshotRecord]:
        """List all available snapshots.

        Returns:
            List of snapshot records sorted by turn number.
        """
        try:
            self.initialize()
            result = self._run_git("tag", "-l", "--sort=creatordate")
            tags = result.stdout.strip().split("\n") if result.stdout.strip() else []

            records = []
            for tag in tags:
                tag = tag.strip()
                if not tag:
                    continue

                # Parse tag: "pre-turn-N" or "post-turn-N"
                parts = tag.rsplit("-", 1)
                if len(parts) != 2:
                    continue

                phase_part = parts[0]  # "pre-turn" or "post-turn"
                try:
                    turn_number = int(parts[1])
                except ValueError:
                    continue

                phase = phase_part.split("-")[0] if "-" in phase_part else phase_part

                # Get commit hash for this tag
                hash_result = self._run_git("rev-parse", tag, check=False)
                commit_hash = (
                    hash_result.stdout.strip() if hash_result.returncode == 0 else ""
                )

                records.append(
                    SnapshotRecord(
                        tag=tag,
                        turn_number=turn_number,
                        phase=phase,
                        workspace=str(self._workspace),
                        commit_hash=commit_hash,
                    )
                )

            return sorted(records, key=lambda r: (r.turn_number, r.phase))

        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as e:
            logger.warning(f"Failed to list snapshots: {e}")
            return []

    def _prune_old_snapshots(self) -> int:
        """Remove snapshots older than max_age_days.

        Returns:
            Number of snapshots pruned.
        """
        if self._max_age_days <= 0:
            return 0

        cutoff = time.time() - (self._max_age_days * 86400)
        pruned = 0

        try:
            result = self._run_git(
                "for-each-ref",
                "--sort=creatordate",
                "--format=%(refname:short) %(creatordate:unix)",
                "refs/tags/",
            )

            for line in result.stdout.strip().split("\n"):
                if not line.strip():
                    continue
                parts = line.strip().split()
                if len(parts) < 2:
                    continue

                tag_name = parts[0]
                try:
                    created_at = float(parts[1])
                except ValueError:
                    continue

                if created_at < cutoff:
                    self._run_git("tag", "-d", tag_name, check=False)
                    pruned += 1

            if pruned > 0:
                # Garbage collect orphaned objects
                self._run_git("gc", "--prune=now", check=False)
                logger.info(f"Pruned {pruned} old snapshots")

        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as e:
            logger.warning(f"Failed to prune snapshots: {e}")

        return pruned

    def get_diff(self, from_turn: int, to_turn: int | None = None) -> str:
        """Get the diff between two snapshots.

        Args:
            from_turn: The starting turn number.
            to_turn: The ending turn number (defaults to current working tree).

        Returns:
            The unified diff string.
        """
        try:
            self.initialize()
            from_tag = f"pre-turn-{from_turn}"

            if to_turn is not None:
                to_tag = f"post-turn-{to_turn}"
                result = self._run_git("diff", from_tag, to_tag, check=False)
            else:
                result = self._run_git("diff", from_tag, check=False)

            return result.stdout

        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as e:
            logger.warning(f"Failed to get diff: {e}")
            return ""
