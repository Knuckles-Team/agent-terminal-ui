"""Workspace boundary enforcement and trust mode.

Configurable sandbox modes for file operations with trust mode toggle.
Modeled after DeepSeek-TUI's workspace boundary system.

Concept: TUI-8 (Workspace Boundary)
"""

from __future__ import annotations

import logging
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class SandboxMode(Enum):
    """Workspace sandbox access levels."""

    READ_ONLY = "read-only"
    WORKSPACE_WRITE = "workspace-write"
    DANGER_FULL_ACCESS = "danger-full-access"


class FileOperation(Enum):
    """Types of file operations."""

    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    EXECUTE = "execute"
    CREATE = "create"


class PolicyViolation:
    """Records a workspace policy violation."""

    def __init__(
        self, operation: FileOperation, path: str, sandbox: SandboxMode, reason: str
    ) -> None:
        self.operation = operation
        self.path = path
        self.sandbox = sandbox
        self.reason = reason

    def __str__(self) -> str:
        return (
            f"[{self.sandbox.value}] {self.operation.value} blocked on "
            f"{self.path}: {self.reason}"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation": self.operation.value,
            "path": self.path,
            "sandbox": self.sandbox.value,
            "reason": self.reason,
        }


class WorkspacePolicy:
    """Enforces workspace boundary and sandbox policies.

    Controls what file operations are allowed based on the configured
    sandbox mode, workspace path, and trust state.
    """

    def __init__(
        self,
        workspace: str | Path,
        sandbox_mode: SandboxMode = SandboxMode.WORKSPACE_WRITE,
        trust_mode: bool = False,
    ) -> None:
        """Initialize the workspace policy.

        Args:
            workspace: The workspace root directory.
            sandbox_mode: The sandbox access level.
            trust_mode: Whether trust mode is enabled (bypasses non-destructive checks).
        """
        self._workspace = Path(workspace).resolve()
        self._sandbox_mode = sandbox_mode
        self._trust_mode = trust_mode
        self._violations: list[PolicyViolation] = []
        self._allowed_paths: set[str] = set()
        self._denied_paths: set[str] = set()

    @property
    def workspace(self) -> Path:
        return self._workspace

    @property
    def sandbox_mode(self) -> SandboxMode:
        return self._sandbox_mode

    @sandbox_mode.setter
    def sandbox_mode(self, mode: SandboxMode) -> None:
        self._sandbox_mode = mode
        logger.info(f"Sandbox mode changed to: {mode.value}")

    @property
    def trust_mode(self) -> bool:
        return self._trust_mode

    @trust_mode.setter
    def trust_mode(self, enabled: bool) -> None:
        self._trust_mode = enabled
        logger.info(f"Trust mode {'enabled' if enabled else 'disabled'}")

    @property
    def violations(self) -> list[PolicyViolation]:
        return self._violations

    def add_allowed_path(self, path: str) -> None:
        """Add an explicitly allowed path (e.g. temp directories)."""
        self._allowed_paths.add(str(Path(path).resolve()))

    def add_denied_path(self, path: str) -> None:
        """Add an explicitly denied path."""
        self._denied_paths.add(str(Path(path).resolve()))

    def check_operation(
        self, operation: FileOperation, path: str | Path
    ) -> PolicyViolation | None:
        """Check if a file operation is allowed.

        Args:
            operation: The type of file operation.
            path: The target file path.

        Returns:
            A PolicyViolation if the operation is blocked, else None.
        """
        resolved = str(Path(path).resolve())

        # Explicit deny list always wins
        for denied in self._denied_paths:
            if resolved.startswith(denied):
                violation = PolicyViolation(
                    operation,
                    resolved,
                    self._sandbox_mode,
                    f"Path is in deny list: {denied}",
                )
                self._violations.append(violation)
                return violation

        # Explicit allow list
        for allowed in self._allowed_paths:
            if resolved.startswith(allowed):
                return None

        # danger-full-access allows everything
        if self._sandbox_mode == SandboxMode.DANGER_FULL_ACCESS:
            return None

        # Trust mode bypasses workspace boundary for reads
        if self._trust_mode and operation == FileOperation.READ:
            return None

        # Read-only mode blocks all writes
        if self._sandbox_mode == SandboxMode.READ_ONLY:
            if operation in (
                FileOperation.WRITE,
                FileOperation.DELETE,
                FileOperation.CREATE,
                FileOperation.EXECUTE,
            ):
                violation = PolicyViolation(
                    operation,
                    resolved,
                    self._sandbox_mode,
                    "Read-only mode blocks write operations",
                )
                self._violations.append(violation)
                return violation
            return None

        # workspace-write mode: check if path is within workspace
        if self._sandbox_mode == SandboxMode.WORKSPACE_WRITE:
            workspace_str = str(self._workspace)
            if operation in (
                FileOperation.WRITE,
                FileOperation.DELETE,
                FileOperation.CREATE,
            ):
                if not resolved.startswith(workspace_str):
                    violation = PolicyViolation(
                        operation,
                        resolved,
                        self._sandbox_mode,
                        f"Path is outside workspace: {workspace_str}",
                    )
                    self._violations.append(violation)
                    return violation

        return None

    def is_within_workspace(self, path: str | Path) -> bool:
        """Check if a path is within the workspace directory."""
        resolved = Path(path).resolve()
        try:
            resolved.relative_to(self._workspace)
            return True
        except ValueError:
            return False

    def get_status(self) -> dict[str, Any]:
        """Get the current policy status."""
        return {
            "workspace": str(self._workspace),
            "sandbox_mode": self._sandbox_mode.value,
            "trust_mode": self._trust_mode,
            "violations_count": len(self._violations),
            "allowed_paths": list(self._allowed_paths),
            "denied_paths": list(self._denied_paths),
        }

    def clear_violations(self) -> None:
        """Clear the violations log."""
        self._violations.clear()
