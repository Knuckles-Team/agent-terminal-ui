"""Lifecycle hooks for session and tool events.

Runs shell commands on lifecycle events (session start/end, tool calls,
mode changes) with timeout protection. Inspired by DeepSeek-TUI's hooks.

Concept: TUI-6 (Lifecycle Hooks)
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_HOOKS_DIR = Path.home() / ".config" / "agent-terminal-ui"
DEFAULT_HOOKS_FILE = DEFAULT_HOOKS_DIR / "hooks.toml"

VALID_EVENTS = frozenset(
    {
        "session_start",
        "session_end",
        "message_submit",
        "tool_call_before",
        "tool_call_after",
        "mode_change",
        "on_error",
        "shell_env",
    }
)


@dataclass
class HookDefinition:
    """A configured lifecycle hook."""

    name: str = ""
    event: str = ""
    command: str = ""
    timeout_secs: int = 30
    enabled: bool = True
    condition: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HookDefinition:
        return cls(
            name=data.get("name", ""),
            event=data.get("event", ""),
            command=data.get("command", ""),
            timeout_secs=data.get("timeout_secs", 30),
            enabled=data.get("enabled", True),
            condition=data.get("condition", {}),
        )


@dataclass
class HookResult:
    """Result of a hook execution."""

    hook_name: str
    event: str
    success: bool
    stdout: str = ""
    stderr: str = ""
    exit_code: int = -1
    duration_ms: int = 0
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "hook_name": self.hook_name,
            "event": self.event,
            "success": self.success,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_code": self.exit_code,
            "duration_ms": self.duration_ms,
            "error": self.error,
        }


class HookManager:
    """Manages lifecycle hooks with timeout-protected execution.

    Hooks are defined in TOML config at
    ``~/.config/agent-terminal-ui/hooks.toml``. Each hook specifies an
    event trigger and a shell command to execute.
    """

    def __init__(
        self,
        hooks_file: Path | None = None,
        default_timeout: int = 30,
        enabled: bool = True,
    ) -> None:
        self._hooks_file = hooks_file or DEFAULT_HOOKS_FILE
        self._default_timeout = default_timeout
        self._enabled = enabled
        self._hooks: list[HookDefinition] = []
        self._history: list[HookResult] = []
        self._load_hooks()

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value

    @property
    def hooks(self) -> list[HookDefinition]:
        return self._hooks

    @property
    def history(self) -> list[HookResult]:
        return self._history

    def _load_hooks(self) -> None:
        """Load hooks from the TOML config file."""
        if not self._hooks_file.exists():
            return

        try:
            import tomllib

            with self._hooks_file.open("rb") as f:
                config = tomllib.load(f)

            hooks_config = config.get("hooks", {})
            self._enabled = hooks_config.get("enabled", self._enabled)
            self._default_timeout = hooks_config.get(
                "default_timeout_secs", self._default_timeout
            )

            for hook_data in hooks_config.get("hooks", []):
                hook = HookDefinition.from_dict(hook_data)
                if not hook.timeout_secs:
                    hook.timeout_secs = self._default_timeout
                if hook.event in VALID_EVENTS:
                    self._hooks.append(hook)
                else:
                    logger.warning(f"Unknown hook event: {hook.event}")

            logger.info(f"Loaded {len(self._hooks)} hooks from {self._hooks_file}")
        except Exception as e:
            logger.warning(f"Failed to load hooks config: {e}")

    def register_hook(self, hook: HookDefinition) -> None:
        """Register a hook programmatically.

        Args:
            hook: The hook definition to register.
        """
        if hook.event in VALID_EVENTS:
            self._hooks.append(hook)

    async def fire(
        self,
        event: str,
        context: dict[str, Any] | None = None,
    ) -> list[HookResult]:
        """Fire all hooks for an event.

        Args:
            event: The lifecycle event name.
            context: Optional context data passed as environment variables.

        Returns:
            List of hook execution results.
        """
        if not self._enabled:
            return []

        matching = [h for h in self._hooks if h.event == event and h.enabled]
        if not matching:
            return []

        results = []
        for hook in matching:
            if not self._check_condition(hook, context):
                continue
            result = await self._execute_hook(hook, context)
            results.append(result)
            self._history.append(result)

        return results

    async def fire_shell_env(
        self, context: dict[str, Any] | None = None
    ) -> dict[str, str]:
        """Fire shell_env hooks and collect environment variables.

        Returns:
            Merged environment variables from all shell_env hooks.
        """
        env_vars: dict[str, str] = {}
        results = await self.fire("shell_env", context)

        for result in results:
            if result.success and result.stdout:
                for line in result.stdout.strip().split("\n"):
                    line = line.strip()
                    if line.startswith("export "):
                        line = line[7:]
                    if "=" in line:
                        key, _, value = line.partition("=")
                        key = key.strip()
                        value = value.strip().strip("'\"")
                        if key:
                            env_vars[key] = value

        return env_vars

    async def _execute_hook(
        self,
        hook: HookDefinition,
        context: dict[str, Any] | None = None,
    ) -> HookResult:
        """Execute a single hook with timeout protection."""
        start = time.time()
        name = hook.name or hook.command[:30]

        try:
            env = {**os.environ}
            if context:
                for k, v in context.items():
                    if isinstance(v, str):
                        env[f"HOOK_{k.upper()}"] = v

            proc = await asyncio.create_subprocess_shell(
                hook.command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )

            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=hook.timeout_secs
            )

            duration_ms = int((time.time() - start) * 1000)
            return HookResult(
                hook_name=name,
                event=hook.event,
                success=proc.returncode == 0,
                stdout=stdout.decode("utf-8", errors="replace") if stdout else "",
                stderr=stderr.decode("utf-8", errors="replace") if stderr else "",
                exit_code=proc.returncode or 0,
                duration_ms=duration_ms,
            )
        except TimeoutError:
            duration_ms = int((time.time() - start) * 1000)
            return HookResult(
                hook_name=name,
                event=hook.event,
                success=False,
                error=f"Timed out after {hook.timeout_secs}s",
                duration_ms=duration_ms,
            )
        except Exception as e:
            duration_ms = int((time.time() - start) * 1000)
            return HookResult(
                hook_name=name,
                event=hook.event,
                success=False,
                error=str(e),
                duration_ms=duration_ms,
            )

    def _check_condition(
        self, hook: HookDefinition, context: dict[str, Any] | None
    ) -> bool:
        """Check if a hook's condition is met."""
        if not hook.condition:
            return True
        if not context:
            return True

        cond_type = hook.condition.get("type", "")
        if cond_type == "tool_category":
            category = hook.condition.get("category", "")
            return context.get("tool_category", "") == category
        if cond_type == "mode":
            mode = hook.condition.get("mode", "")
            return context.get("mode", "") == mode

        return True
