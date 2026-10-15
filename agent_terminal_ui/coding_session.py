"""Coding session model and local client-capability handlers.

A coding session is rooted in a workspace directory. The agent asks the
terminal to act on the person's host through ACP client capabilities
(``fs/*`` and ``terminal/*``); this module types those requests and serves them
locally. Admission and permission decisions come from ``GRAPHOS-ACP``; the view
holds no policy of its own beyond path containment in the workspace root.

Concept: TUI-RUNTIME-R011 (Coding session in the local workspace)
"""

from __future__ import annotations

import asyncio
import contextlib
import os
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from agent_terminal_ui.workspace_policy import (
    FileOperation,
    SandboxMode,
    WorkspacePolicy,
)

DEFAULT_OUTPUT_LIMIT = 1_000_000


class ClientCapability(StrEnum):
    """The closed set of client-capability methods the terminal can serve."""

    FS_READ_TEXT_FILE = "fs/read_text_file"
    FS_WRITE_TEXT_FILE = "fs/write_text_file"
    TERMINAL_CREATE = "terminal/create"
    TERMINAL_OUTPUT = "terminal/output"
    TERMINAL_WAIT_FOR_EXIT = "terminal/wait_for_exit"
    TERMINAL_KILL = "terminal/kill"


class RefusalReason(StrEnum):
    """Why a client-capability request was refused."""

    UNKNOWN_METHOD = "unknown_method"
    NOT_GRANTED = "not_granted"
    OUTSIDE_ROOT = "outside_root"
    INVALID_PARAMS = "invalid_params"
    FAILED = "failed"


@dataclass(frozen=True)
class CapabilityRefusal:
    """Typed refusal returned instead of a result."""

    reason: RefusalReason
    detail: str = ""

    def to_dict(self) -> dict[str, str]:
        return {"refused": self.reason.value, "detail": self.detail}


CapabilityResult = dict[str, Any] | CapabilityRefusal


@dataclass
class _Terminal:
    process: asyncio.subprocess.Process
    limit: int
    output: bytearray = field(default_factory=bytearray)
    truncated: bool = False
    pump: asyncio.Task[None] | None = None

    async def collect(self) -> None:
        """Drain the process output into the bounded buffer."""
        stream = self.process.stdout
        if stream is None:
            return
        while chunk := await stream.read(65536):
            room = self.limit - len(self.output)
            if room < len(chunk):
                self.truncated = True
            self.output.extend(chunk[: max(room, 0)])


@dataclass
class LocalTerminals:
    """Host processes created for the session, keyed by terminal ID."""

    _items: dict[str, _Terminal] = field(default_factory=dict)
    _counter: int = 0

    def add(self, terminal: _Terminal) -> str:
        self._counter += 1
        terminal_id = f"term-{self._counter}"
        self._items[terminal_id] = terminal
        return terminal_id

    def get(self, terminal_id: object) -> _Terminal | None:
        return self._items.get(str(terminal_id))


Handler = Callable[["CodingSessionView", dict[str, Any]], Awaitable[CapabilityResult]]


def _refuse(reason: RefusalReason, detail: str = "") -> CapabilityRefusal:
    return CapabilityRefusal(reason, detail)


def _contained_path(
    view: CodingSessionView, raw: object, operation: FileOperation
) -> Path | CapabilityRefusal:
    """Resolve ``raw`` (symlinks followed) and refuse anything outside the root."""
    if not isinstance(raw, str) or not raw:
        return _refuse(RefusalReason.INVALID_PARAMS, "path must be a string")
    target = view.root / raw
    violation = view.policy.check_operation(operation, target, contained=True)
    if violation is not None:
        return _refuse(RefusalReason.OUTSIDE_ROOT, violation.reason)
    return target.resolve()


async def read_text_file(
    view: CodingSessionView, params: dict[str, Any]
) -> CapabilityResult:
    """Default ``fs/read_text_file``: return file text, no prompt inside the root."""
    path = _contained_path(view, params.get("path"), FileOperation.READ)
    if isinstance(path, CapabilityRefusal):
        return path
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return _refuse(RefusalReason.FAILED, str(exc))
    line, limit = params.get("line"), params.get("limit")
    if isinstance(line, int) or isinstance(limit, int):
        start = max(line - 1, 0) if isinstance(line, int) else 0
        lines = text.splitlines(keepends=True)[start:]
        text = "".join(lines[:limit] if isinstance(limit, int) else lines)
    return {"content": text}


async def write_text_file(
    view: CodingSessionView, params: dict[str, Any]
) -> CapabilityResult:
    """Default ``fs/write_text_file``: write text inside the root."""
    path = _contained_path(view, params.get("path"), FileOperation.WRITE)
    if isinstance(path, CapabilityRefusal):
        return path
    content = params.get("content")
    if not isinstance(content, str):
        return _refuse(RefusalReason.INVALID_PARAMS, "content must be a string")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    except OSError as exc:
        return _refuse(RefusalReason.FAILED, str(exc))
    return {}


async def terminal_create(
    view: CodingSessionView, params: dict[str, Any]
) -> CapabilityResult:
    """Default ``terminal/create``: start a host process in the root."""
    command = params.get("command")
    if not isinstance(command, str) or not command:
        return _refuse(RefusalReason.INVALID_PARAMS, "command must be a string")
    cwd = _contained_path(view, params.get("cwd", "."), FileOperation.EXECUTE)
    if isinstance(cwd, CapabilityRefusal):
        return cwd
    args = [str(a) for a in params.get("args") or []]
    env = {
        **os.environ,
        **{str(e["name"]): str(e["value"]) for e in params.get("env") or []},
    }
    try:
        process = await asyncio.create_subprocess_exec(
            command,
            *args,
            cwd=cwd,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
    except OSError as exc:
        return _refuse(RefusalReason.FAILED, str(exc))
    limit = params.get("outputByteLimit")
    terminal = _Terminal(
        process, limit if isinstance(limit, int) else DEFAULT_OUTPUT_LIMIT
    )
    terminal.pump = asyncio.ensure_future(terminal.collect())
    return {"terminalId": view.terminals.add(terminal)}


def _exit_status(process: asyncio.subprocess.Process) -> dict[str, Any] | None:
    code = process.returncode
    if code is None:
        return None
    return {
        "exitCode": code if code >= 0 else None,
        "signal": -code if code < 0 else None,
    }


def _terminal_for(
    view: CodingSessionView, params: dict[str, Any]
) -> _Terminal | CapabilityRefusal:
    terminal = view.terminals.get(params.get("terminalId"))
    if terminal is None:
        return _refuse(RefusalReason.INVALID_PARAMS, "unknown terminalId")
    return terminal


async def terminal_output(
    view: CodingSessionView, params: dict[str, Any]
) -> CapabilityResult:
    """Default ``terminal/output``: output captured so far."""
    terminal = _terminal_for(view, params)
    if isinstance(terminal, CapabilityRefusal):
        return terminal
    return {
        "output": terminal.output.decode("utf-8", errors="replace"),
        "truncated": terminal.truncated,
        "exitStatus": _exit_status(terminal.process),
    }


async def terminal_wait_for_exit(
    view: CodingSessionView, params: dict[str, Any]
) -> CapabilityResult:
    """Default ``terminal/wait_for_exit``: block until the process exits."""
    terminal = _terminal_for(view, params)
    if isinstance(terminal, CapabilityRefusal):
        return terminal
    await terminal.process.wait()
    if terminal.pump is not None:
        await terminal.pump
    return _exit_status(terminal.process) or {}


async def terminal_kill(
    view: CodingSessionView, params: dict[str, Any]
) -> CapabilityResult:
    """Default ``terminal/kill``: terminate the process, keep its output."""
    terminal = _terminal_for(view, params)
    if isinstance(terminal, CapabilityRefusal):
        return terminal
    with contextlib.suppress(ProcessLookupError):
        terminal.process.kill()
    return {}


DEFAULT_HANDLERS: dict[ClientCapability, Handler] = {
    ClientCapability.FS_READ_TEXT_FILE: read_text_file,
    ClientCapability.FS_WRITE_TEXT_FILE: write_text_file,
    ClientCapability.TERMINAL_CREATE: terminal_create,
    ClientCapability.TERMINAL_OUTPUT: terminal_output,
    ClientCapability.TERMINAL_WAIT_FOR_EXIT: terminal_wait_for_exit,
    ClientCapability.TERMINAL_KILL: terminal_kill,
}


@dataclass
class CodingSessionView:
    """State of one coding session: root, granted capabilities, pending request."""

    root: Path
    capabilities: frozenset[ClientCapability]
    session_id: str
    pending: dict[str, Any] | None = None
    handlers: dict[ClientCapability, Handler] = field(
        default_factory=lambda: dict(DEFAULT_HANDLERS)
    )
    terminals: LocalTerminals = field(default_factory=LocalTerminals)
    policy: WorkspacePolicy = field(init=False)

    def __post_init__(self) -> None:
        self.root = Path(self.root).resolve()
        self.policy = WorkspacePolicy(
            self.root, SandboxMode.WORKSPACE_WRITE, trust_mode=False
        )

    @classmethod
    def open(
        cls,
        root: str | Path,
        session_id: str,
        capabilities: Iterable[str] | None = None,
    ) -> CodingSessionView:
        """Open a session; unknown capability names are dropped, never granted."""
        known = {c.value: c for c in ClientCapability}
        names = known if capabilities is None else capabilities
        granted = frozenset(known[n] for n in names if n in known)
        return cls(Path(root), granted, session_id)

    async def handle(self, method: str, params: dict[str, Any]) -> CapabilityResult:
        """Serve one client-capability request, or return a typed refusal."""
        try:
            capability = ClientCapability(method)
        except ValueError:
            return _refuse(RefusalReason.UNKNOWN_METHOD, method)
        if capability not in self.capabilities:
            return _refuse(RefusalReason.NOT_GRANTED, method)
        self.pending = {"method": method, "params": params}
        try:
            return await self.handlers[capability](self, params)
        finally:
            self.pending = None
