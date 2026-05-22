"""Tests for hooks.py -- Lifecycle hooks system."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_terminal_ui.hooks import (
    HookDefinition,
    HookManager,
    HookResult,
    VALID_EVENTS,
)


class TestHookDefinition:
    def test_from_dict(self) -> None:
        data = {
            "name": "test-hook",
            "event": "session_start",
            "command": "echo hello",
            "timeout_secs": 10,
        }
        hook = HookDefinition.from_dict(data)
        assert hook.name == "test-hook"
        assert hook.event == "session_start"
        assert hook.command == "echo hello"
        assert hook.timeout_secs == 10

    def test_defaults(self) -> None:
        hook = HookDefinition.from_dict({})
        assert hook.enabled is True
        assert hook.timeout_secs == 30


class TestHookResult:
    def test_to_dict(self) -> None:
        result = HookResult(
            hook_name="test",
            event="session_start",
            success=True,
            stdout="output",
            exit_code=0,
        )
        d = result.to_dict()
        assert d["success"] is True
        assert d["stdout"] == "output"


class TestHookManager:
    def test_init_no_config(self, tmp_path: Path) -> None:
        mgr = HookManager(hooks_file=tmp_path / "nonexistent.toml")
        assert len(mgr.hooks) == 0

    def test_register_hook(self) -> None:
        mgr = HookManager(hooks_file=Path("/nonexistent"))
        hook = HookDefinition(name="test", event="session_start", command="echo hi")
        mgr.register_hook(hook)
        assert len(mgr.hooks) == 1

    def test_register_invalid_event(self) -> None:
        mgr = HookManager(hooks_file=Path("/nonexistent"))
        hook = HookDefinition(name="bad", event="invalid_event", command="echo")
        mgr.register_hook(hook)
        # Invalid events are silently ignored
        assert len(mgr.hooks) == 0

    def test_enabled_toggle(self) -> None:
        mgr = HookManager(hooks_file=Path("/nonexistent"))
        assert mgr.enabled is True
        mgr.enabled = False
        assert mgr.enabled is False

    @pytest.mark.asyncio
    async def test_fire_disabled(self) -> None:
        mgr = HookManager(hooks_file=Path("/nonexistent"), enabled=False)
        hook = HookDefinition(name="test", event="session_start", command="echo hi")
        mgr.register_hook(hook)
        results = await mgr.fire("session_start")
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_fire_no_matching_hooks(self) -> None:
        mgr = HookManager(hooks_file=Path("/nonexistent"))
        results = await mgr.fire("session_start")
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_fire_echo(self) -> None:
        mgr = HookManager(hooks_file=Path("/nonexistent"))
        hook = HookDefinition(
            name="echo-test", event="session_start", command="echo hello"
        )
        mgr.register_hook(hook)
        results = await mgr.fire("session_start")
        assert len(results) == 1
        assert results[0].success is True
        assert "hello" in results[0].stdout

    @pytest.mark.asyncio
    async def test_fire_timeout(self) -> None:
        mgr = HookManager(hooks_file=Path("/nonexistent"))
        hook = HookDefinition(
            name="slow", event="session_start", command="sleep 10", timeout_secs=1
        )
        mgr.register_hook(hook)
        results = await mgr.fire("session_start")
        assert len(results) == 1
        assert results[0].success is False
        assert "Timed out" in results[0].error

    @pytest.mark.asyncio
    async def test_fire_failed_command(self) -> None:
        mgr = HookManager(hooks_file=Path("/nonexistent"))
        hook = HookDefinition(name="fail", event="session_start", command="exit 1")
        mgr.register_hook(hook)
        results = await mgr.fire("session_start")
        assert len(results) == 1
        assert results[0].success is False
        assert results[0].exit_code == 1

    @pytest.mark.asyncio
    async def test_fire_shell_env(self) -> None:
        mgr = HookManager(hooks_file=Path("/nonexistent"))
        hook = HookDefinition(
            name="env", event="shell_env", command='echo "FOO=bar\nBAZ=qux"'
        )
        mgr.register_hook(hook)
        env_vars = await mgr.fire_shell_env()
        assert env_vars.get("FOO") == "bar"
        assert env_vars.get("BAZ") == "qux"

    @pytest.mark.asyncio
    async def test_history_tracking(self) -> None:
        mgr = HookManager(hooks_file=Path("/nonexistent"))
        hook = HookDefinition(
            name="track", event="session_start", command="echo tracked"
        )
        mgr.register_hook(hook)
        await mgr.fire("session_start")
        assert len(mgr.history) == 1

    @pytest.mark.asyncio
    async def test_condition_tool_category(self) -> None:
        mgr = HookManager(hooks_file=Path("/nonexistent"))
        hook = HookDefinition(
            name="shell-only",
            event="tool_call_before",
            command="echo matched",
            condition={"type": "tool_category", "category": "shell"},
        )
        mgr.register_hook(hook)

        # Should match
        results = await mgr.fire("tool_call_before", {"tool_category": "shell"})
        assert len(results) == 1

        # Should not match
        results = await mgr.fire("tool_call_before", {"tool_category": "file"})
        assert len(results) == 0

    def test_load_toml_config(self, tmp_path: Path) -> None:
        config = tmp_path / "hooks.toml"
        config.write_text("""
[hooks]
enabled = true
default_timeout_secs = 15

[[hooks.hooks]]
name = "startup"
event = "session_start"
command = "echo started"
""")
        mgr = HookManager(hooks_file=config)
        assert len(mgr.hooks) == 1
        assert mgr.hooks[0].name == "startup"


class TestValidEvents:
    def test_all_events_present(self) -> None:
        expected = {
            "session_start",
            "session_end",
            "message_submit",
            "tool_call_before",
            "tool_call_after",
            "mode_change",
            "on_error",
            "shell_env",
        }
        assert VALID_EVENTS == expected
