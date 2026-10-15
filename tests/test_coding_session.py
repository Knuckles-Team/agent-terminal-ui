"""Tests for the coding session model and local client-capability handlers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from agent_terminal_ui.coding_session import (
    CapabilityRefusal,
    ClientCapability,
    CodingSessionView,
    RefusalReason,
)
from agent_terminal_ui.workspace_policy import FileOperation


def _view(root: Path, trust: bool = False) -> CodingSessionView:
    view = CodingSessionView.open(root, "s1")
    view.policy.trust_mode = trust
    return view


def _refusal(result: Any) -> CapabilityRefusal:
    assert isinstance(result, CapabilityRefusal)
    return result


@pytest.mark.spec("TUI-RUNTIME-R011.1")
async def test_session_model_closed_capability_set(tmp_path: Path) -> None:
    assert {c.value for c in ClientCapability} == {
        "fs/read_text_file",
        "fs/write_text_file",
        "terminal/create",
        "terminal/output",
        "terminal/wait_for_exit",
        "terminal/kill",
    }
    view = CodingSessionView.open(tmp_path, "s1", ["fs/read_text_file", "fs/delete"])
    assert view.capabilities == {ClientCapability.FS_READ_TEXT_FILE}
    assert view.root == tmp_path.resolve()
    assert view.session_id == "s1"
    assert view.pending is None
    unknown = _refusal(await view.handle("fs/delete", {"path": "a"}))
    assert unknown.reason is RefusalReason.UNKNOWN_METHOD
    ungranted = _refusal(await view.handle("terminal/kill", {}))
    assert ungranted.reason is RefusalReason.NOT_GRANTED


@pytest.mark.spec("TUI-RUNTIME-R011.2")
async def test_capability_handlers_serve_local_host(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("one\ntwo\nthree\n")
    view = _view(tmp_path)
    prompts: list[str] = []

    async def read_with_prompt_probe(
        view: CodingSessionView, params: dict[str, Any]
    ) -> Any:
        prompts.extend(str(r) for r in [view.pending] if r and "prompt" in r)
        return await default_read(view, params)

    default_read = view.handlers[ClientCapability.FS_READ_TEXT_FILE]
    view.handlers[ClientCapability.FS_READ_TEXT_FILE] = read_with_prompt_probe
    read = await view.handle("fs/read_text_file", {"path": "a.txt"})
    assert read == {"content": "one\ntwo\nthree\n"}
    sliced = await view.handle(
        "fs/read_text_file", {"path": "a.txt", "line": 2, "limit": 1}
    )
    assert sliced == {"content": "two\n"}
    assert prompts == []

    assert (
        await view.handle("fs/write_text_file", {"path": "sub/b.txt", "content": "hi"})
        == {}
    )
    assert (tmp_path / "sub" / "b.txt").read_text() == "hi"

    created = await view.handle(
        "terminal/create", {"command": "sh", "args": ["-c", "echo hello; exit 3"]}
    )
    assert isinstance(created, dict)
    tid = created["terminalId"]
    status = await view.handle("terminal/wait_for_exit", {"terminalId": tid})
    assert status == {"exitCode": 3, "signal": None}
    out = await view.handle("terminal/output", {"terminalId": tid})
    assert isinstance(out, dict)
    assert out["output"] == "hello\n"
    assert out["exitStatus"] == {"exitCode": 3, "signal": None}

    sleeper = await view.handle("terminal/create", {"command": "sleep", "args": ["30"]})
    assert isinstance(sleeper, dict)
    await view.handle("terminal/kill", {"terminalId": sleeper["terminalId"]})
    killed = await view.handle(
        "terminal/wait_for_exit", {"terminalId": sleeper["terminalId"]}
    )
    assert killed == {"exitCode": None, "signal": 9}
    bad = _refusal(await view.handle("terminal/output", {"terminalId": "nope"}))
    assert bad.reason is RefusalReason.INVALID_PARAMS


@pytest.mark.spec("TUI-RUNTIME-R011.3")
@pytest.mark.parametrize("trust", [False, True])
async def test_path_containment_refuses_escape(tmp_path: Path, trust: bool) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("secret")
    (root / "link").symlink_to(outside)
    (root / "dirlink").symlink_to(tmp_path)
    view = _view(root, trust)

    for path in ("../outside.txt", str(outside), "link", "dirlink/outside.txt"):
        refusal = _refusal(await view.handle("fs/read_text_file", {"path": path}))
        assert refusal.reason is RefusalReason.OUTSIDE_ROOT, path
        refusal = _refusal(
            await view.handle("fs/write_text_file", {"path": path, "content": "x"})
        )
        assert refusal.reason is RefusalReason.OUTSIDE_ROOT, path
    assert outside.read_text() == "secret"
    assert not (tmp_path / "new.txt").exists()
    escape = _refusal(
        await view.handle("terminal/create", {"command": "true", "cwd": "../"})
    )
    assert escape.reason is RefusalReason.OUTSIDE_ROOT
    sibling = tmp_path / "root2"
    sibling.mkdir()
    assert (
        view.policy.check_operation(FileOperation.READ, sibling, contained=True)
        is not None
    )
