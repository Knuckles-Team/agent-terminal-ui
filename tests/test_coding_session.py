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
    view = CodingSessionView.open(root, "s1", [c.value for c in ClientCapability])
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


@pytest.mark.parametrize("capabilities", [None, [], ["fs/delete"]])
async def test_missing_capabilities_never_reach_host_handlers(
    tmp_path: Path, capabilities: list[str] | None
) -> None:
    view = CodingSessionView.open(tmp_path, "s1", capabilities)

    async def forbidden(view: CodingSessionView, params: dict[str, Any]) -> Any:
        pytest.fail("ungranted request reached a host handler")

    view.handlers = {capability: forbidden for capability in ClientCapability}
    for capability in ClientCapability:
        result = _refusal(await view.handle(capability.value, {"path": "a.txt"}))
        assert result.reason is RefusalReason.NOT_GRANTED
        assert view.pending is None


@pytest.mark.parametrize("trust", [False, True])
async def test_escaping_reads_touch_no_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, trust: bool
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "secret"
    outside.write_text("secret")
    (root / "link").symlink_to(outside)
    view = CodingSessionView.open(root, "s1", ["fs/read_text_file"])
    view.policy.trust_mode = trust

    def forbidden(*args: Any, **kwargs: Any) -> str:
        raise AssertionError("escaping read accessed file bytes")

    monkeypatch.setattr(Path, "read_text", forbidden)
    for path in ("../secret", str(outside), "link"):
        result = _refusal(await view.handle("fs/read_text_file", {"path": path}))
        assert result.reason is RefusalReason.OUTSIDE_ROOT
        assert view.pending is None


@pytest.mark.parametrize(
    "window",
    [{"line": True}, {"line": 0}, {"line": -1}, {"line": "1"},
     {"limit": False}, {"limit": -1}, {"limit": 1.5}],
)
async def test_invalid_read_windows_touch_no_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, window: dict[str, Any]
) -> None:
    view = CodingSessionView.open(tmp_path, "s1", ["fs/read_text_file"])

    def forbidden(*args: Any, **kwargs: Any) -> str:
        raise AssertionError("invalid read window accessed file bytes")

    monkeypatch.setattr(Path, "read_text", forbidden)
    result = _refusal(await view.handle("fs/read_text_file", {"path": "a", **window}))
    assert result.reason is RefusalReason.INVALID_PARAMS
    assert view.pending is None


async def test_explicit_read_grant_preserves_line_window(tmp_path: Path) -> None:
    (tmp_path / "a").write_text("one\ntwo\nthree\n")
    view = CodingSessionView.open(tmp_path, "s1", ["fs/read_text_file"])
    assert await view.handle("fs/read_text_file", {"path": "a", "line": 2, "limit": 1}) == {
        "content": "two\n"
    }
    assert await view.handle("fs/read_text_file", {"path": "a", "limit": 0}) == {
        "content": ""
    }
    result = _refusal(await view.handle("fs/write_text_file", {"path": "a", "content": "x"}))
    assert result.reason is RefusalReason.NOT_GRANTED
    assert (tmp_path / "a").read_text() == "one\ntwo\nthree\n"


async def test_nul_path_refuses_before_resolution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    view = CodingSessionView.open(tmp_path, "s1", ["fs/read_text_file"])

    def forbidden(*args: Any, **kwargs: Any) -> Path:
        raise AssertionError("invalid path reached resolution")

    with monkeypatch.context() as patch:
        patch.setattr(Path, "resolve", forbidden)
        result = _refusal(await view.handle("fs/read_text_file", {"path": "bad\x00name"}))
    assert result.reason is RefusalReason.INVALID_PARAMS
    assert view.pending is None


@pytest.mark.parametrize("error", [OSError, RuntimeError, ValueError])
async def test_path_resolution_error_is_typed_and_clears_pending(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error: type[Exception]
) -> None:
    view = CodingSessionView.open(tmp_path, "s1", ["fs/read_text_file"])
    (tmp_path / "a").write_text("ok")

    def failed_resolution(*args: Any, **kwargs: Any) -> Path:
        raise error("resolution unavailable")

    def forbidden_read(*args: Any, **kwargs: Any) -> str:
        raise AssertionError("failed resolution reached file bytes")

    with monkeypatch.context() as patch:
        patch.setattr(Path, "resolve", failed_resolution)
        patch.setattr(Path, "read_text", forbidden_read)
        result = _refusal(await view.handle("fs/read_text_file", {"path": "a"}))
    assert result.reason is RefusalReason.FAILED
    assert result.detail == "path resolution failed"
    assert view.pending is None
    assert await view.handle("fs/read_text_file", {"path": "a"}) == {"content": "ok"}


@pytest.mark.parametrize("kind", ["missing", "directory", "invalid_utf8", "symlink_loop"])
async def test_unreadable_files_are_typed_failures(tmp_path: Path, kind: str) -> None:
    view = CodingSessionView.open(tmp_path, "s1", ["fs/read_text_file"])
    path = tmp_path / "a"
    if kind == "directory":
        path.mkdir()
    elif kind == "invalid_utf8":
        path.write_bytes(b"\xff")
    elif kind == "symlink_loop":
        path.symlink_to(path)
    result = _refusal(await view.handle("fs/read_text_file", {"path": "a"}))
    assert result.reason is RefusalReason.FAILED
    assert view.pending is None
