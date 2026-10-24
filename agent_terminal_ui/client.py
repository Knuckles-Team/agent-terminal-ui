#!/usr/bin/python
"""Agent Client implementation for the terminal UI.

Conversation turns use Arbora's authenticated A2A JSON-RPC boundary at
``{base}/a2a``: ``message/stream`` admits one durable task and streams its
state transitions as Server-Sent Events, ``tasks/resubscribe`` re-attaches to
a task after a disconnect, and ``tasks/cancel`` cancels it. When the served
Agent Card advertises ``streaming: false``, a turn is ``message/send``
followed by ``tasks/get`` polling instead. The conversation
(session) identity is the A2A ``contextId`` this client mints; the server owns
every task. Graph and operator capabilities use the Arbora REST gateway.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import math
import os
import re
import sys
import uuid
from collections.abc import AsyncGenerator, Mapping
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit

import httpx

from agent_terminal_ui.capabilities import (
    CapabilityCatalog,
    CapabilityDescriptor,
    CapabilityInvocation,
    CapabilityPreflight,
    RunCatalog,
    RunEventPage,
    RunSummary,
)
from agent_terminal_ui.host_logs import HostLogReader as HostLogReader
from agent_terminal_ui.public_run_events import MAX_SEQUENCE, SCHEMA, identifier

logger = logging.getLogger(__name__)

#: Prefix the gateway mounts the canonical Knowledge-Graph REST table under.
#: The ``/graph/*`` action twins live there, unlike the server's own
#: un-prefixed routers (``/models``, ``/tools``, ``/mcp/*``).
GATEWAY_API_PREFIX = "/api"

#: The Arbora A2A JSON-RPC endpoint and its Agent Card.
A2A_PATH = "/a2a"
AGENT_CARD_PATH = "/.well-known/agent-card.json"

#: The typed Arbora task a TUI mode asks for; Arbora never routes free text.
MODE_TASK_IRIS = {
    "ask": "eg:task/communicate",
    "plan": "eg:task/research",
    "build": "eg:task/implement",
    "code": "eg:task/implement",
}

#: A2A task states that end a stream.
_FINAL_STATES = frozenset({"completed", "canceled", "failed", "rejected"})
_FAILED_STATES = frozenset({"failed", "rejected"})
_STREAM_UNSUPPORTED = frozenset({-32010, -32004, -32601})


class A2ATransportError(RuntimeError):
    """Arbora answered a JSON-RPC request with an error object."""

    def __init__(
        self,
        error: dict[str, Any],
        *,
        status_code: int | None = None,
        acknowledged: bool = False,
    ) -> None:
        super().__init__(str(error.get("message") or "A2A request failed"))
        self.code = error.get("code")
        self.status_code = status_code
        self.acknowledged = acknowledged


class ArboraOperationError(RuntimeError):
    """An operation was refused by the versioned Arbora API."""

    def __init__(self, code: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.details = details or {}


class _OperationTransport:
    """Pass one request's confirmation headers to the generated client."""

    def __init__(self, client: AgentClient, headers: dict[str, str]) -> None:
        self.client = client
        self.headers = headers

    async def invoke(self, op_id: str, params: Mapping[str, Any]) -> dict[str, Any]:
        response = await self.client._http_client.post(
            f"{self.client.base_url}/api/v1/ops/{quote(op_id, safe='.')}",
            json=dict(params),
            headers=self.headers,
        )
        try:
            payload = response.json()
        except ValueError as exc:
            raise ArboraOperationError("INVALID_ENVELOPE") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("ok"), bool):
            raise ArboraOperationError("INVALID_ENVELOPE")
        if payload["ok"]:
            response.raise_for_status()
        return payload


def _sse_frames(lines: list[str]) -> list[dict[str, Any]]:
    """Decode the JSON-RPC frame carried by one SSE event's ``data`` lines."""
    data = "\n".join(line[5:].lstrip() for line in lines if line.startswith("data:"))
    if not data:
        return []
    frame = json.loads(data)
    if not isinstance(frame, dict):
        raise ValueError("A2A frame was not an object")
    return [frame]


def _frame_result(frame: dict[str, Any]) -> dict[str, Any]:
    error = frame.get("error")
    if error is not None and not isinstance(error, dict):
        raise A2ATransportError({"message": "A2A error was not an object"})
    if isinstance(error, dict):
        raise A2ATransportError(error, acknowledged="result" in frame)
    result = frame.get("result")
    if not isinstance(result, dict):
        raise A2ATransportError({"message": "A2A frame carried no result"})
    return result


def _arbora_metadata(result: dict[str, Any]) -> dict[str, Any]:
    metadata = result.get("metadata")
    arbora = metadata.get("arbora") if isinstance(metadata, dict) else None
    return arbora if isinstance(arbora, dict) else {}


def _public_run_metadata_matches(result: dict[str, Any], run_id: str) -> bool:
    metadata = result.get("metadata", {})
    if not isinstance(metadata, dict):
        return False
    arbora = metadata.get("arbora", {})
    return isinstance(arbora, dict) and (
        "runId" not in arbora or arbora["runId"] == run_id
    )


def new_session_id() -> str:
    """Mint a new conversation identity (the A2A ``contextId``)."""
    return f"tui-{uuid.uuid4().hex}"


def _is_approval_operation(op: str) -> bool:
    """Identify the approval namespace while its durable authority is unserved."""
    return op.lower().startswith("approvals.")


def _artifact_events(result: dict[str, Any], session_id: str) -> list[dict[str, Any]]:
    text = _artifact_text(result.get("artifact"))
    if not text:
        return []
    return [
        {
            "type": "text",
            "content": text,
            "session_id": session_id,
            "task_id": result.get("taskId"),
        }
    ]


def _a2a_objects(value: Any, field: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError(f"invalid A2A {field}")
    return value


def _artifact_text(artifact: Any) -> str:
    if not isinstance(artifact, dict):
        raise ValueError("invalid A2A artifact")
    parts = _a2a_objects(artifact.get("parts", []), "parts")
    texts = [
        part.get("text", "") for part in parts if part.get("kind", "text") == "text"
    ]
    if any(not isinstance(text, str) for text in texts):
        raise ValueError("invalid A2A text")
    return "".join(texts)


def _task_answers(task: dict[str, Any]) -> list[dict[str, Any]]:
    history_value = task.get("history")
    artifacts_value = task.get("artifacts")
    history = _a2a_objects([] if history_value is None else history_value, "history")
    artifacts = _a2a_objects(
        [] if artifacts_value is None else artifacts_value, "artifacts"
    )
    for item in history + artifacts:
        _artifact_text(item)
    return artifacts or [item for item in history if item.get("role") == "agent"][-1:]


def _public_task_binding(result: dict[str, Any]) -> dict[str, str] | None:
    """Identify an unavailable placeholder without inferring a backend run."""
    kind = result.get("kind")
    task_key = "id" if kind == "task" else "taskId"
    task_id = result.get(task_key)
    context_id = result.get("contextId")
    status = result.get("status")
    if (
        isinstance(kind, str)
        and kind in {"task", "status-update"}
        and isinstance(status, dict)
        and isinstance(status.get("state"), str)
        and status.get("state")
        in _FINAL_STATES | {"submitted", "working", "input-required", "auth-required"}
        and isinstance(task_id, str)
        and isinstance(context_id, str)
        and identifier(task_id)
        and identifier(context_id)
        and all(key not in result or result[key] == task_id for key in ("id", "taskId"))
    ):
        return {"task_id": task_id, "context_id": context_id}
    return None


def _public_run_binding(result: dict[str, Any]) -> dict[str, str] | None:
    """Keep the server's complete task/context/run binding, never infer a run."""
    task_binding = _public_task_binding(result)
    run_id = _arbora_metadata(result).get("runId")
    if task_binding is not None and isinstance(run_id, str) and identifier(run_id):
        return {**task_binding, "run_id": run_id}
    return None


def _task_state(result: dict[str, Any]) -> str:
    status = result.get("status", {})
    if not isinstance(status, dict):
        raise ValueError("invalid A2A task status")
    state = status.get("state", "")
    if not isinstance(state, str):
        raise ValueError("invalid A2A task state")
    return state


def normalize_a2a_event(
    result: dict[str, Any], session_id: str
) -> list[dict[str, Any]]:
    """Map one A2A task/status event onto the TUI's normalized vocabulary.

    A task and every non-final transition become a ``status`` sideband; a
    final ``completed``/``canceled`` state ends the turn, and a final
    ``failed``/``rejected`` state reports an error before ending it. The
    completed task's answer arrives as an ``artifact-update`` and renders as
    ``text``.
    """
    if result.get("kind") == "artifact-update":
        return _artifact_events(result, session_id)
    task_id = result.get("id") or result.get("taskId")
    state = _task_state(result)
    if result.get("kind") == "task":
        _task_answers(result)
    run_id = _arbora_metadata(result).get("runId")
    common: dict[str, Any] = {"session_id": session_id, "task_id": task_id}
    if run_id:
        common["run_id"] = run_id
    public_binding = _public_run_binding(result)
    if public_binding is not None:
        common["public_run_binding"] = public_binding
    elif task_binding := _public_task_binding(result):
        common["public_task_binding"] = task_binding
    status = {
        "type": "sideband",
        "data": {"type": "status", "state": state, "task_id": task_id},
        **common,
    }
    if state not in _FINAL_STATES or result.get("final") is False:
        return [status]
    events = [status]
    if state in _FAILED_STATES:
        events.append({"type": "error", "message": f"task {state}", **common})
    events.append({"type": "turn_end", "state": state, **common})
    return events


def _poll_binding(task: dict[str, Any]) -> tuple[str, str, str | None]:
    """Bind unary reads to the task returned by admission."""
    task_id, context_id = task.get("id"), task.get("contextId")
    if (
        task.get("kind") != "task"
        or not isinstance(task_id, str)
        or not task_id.strip()
        or not isinstance(context_id, str)
        or not context_id.strip()
    ):
        raise A2ATransportError({"message": "Invalid task correlation"})
    status = task.get("status")
    state = status.get("state") if isinstance(status, dict) else None
    if not isinstance(state, str) or state not in _FINAL_STATES | {
        "submitted",
        "working",
        "input-required",
        "auth-required",
    }:
        raise A2ATransportError({"message": "Invalid task state"})
    run_id = _arbora_metadata(task).get("runId")
    if run_id is not None and (not isinstance(run_id, str) or not run_id.strip()):
        raise A2ATransportError({"message": "Invalid run correlation"})
    return task_id, context_id, run_id


def _candidate_skills_dirs(workspace_root: Path) -> list[Path]:
    """Directories checked, in order, for a universal-skills tree."""
    return [
        workspace_root
        / "ai"
        / "skills"
        / "universal-skills"
        / "universal_skills"
        / "skills",
        workspace_root
        / "agent-packages"
        / "skills"
        / "universal-skills"
        / "universal_skills"
        / "skills",
        Path.home() / ".codeium" / "windsurf" / "skills",
        Path.home() / ".config" / "devin" / "skills",
    ]


def _extract_yaml_frontmatter(lines: list[str]) -> list[str]:
    """Return the raw lines between the first ``---``/``---`` pair, if any."""
    in_yaml = False
    yaml_content: list[str] = []
    for line in lines:
        if line.strip() == "---":
            if not in_yaml:
                in_yaml = True
            else:
                break
        elif in_yaml:
            yaml_content.append(line)
    return yaml_content


def _parse_skill_description(content: str) -> str:
    """Extract a skill's description from its ``SKILL.md`` content.

    Prefers a YAML frontmatter ``description:`` key; falls back to the first
    non-empty, non-marker, non-heading line.
    """
    lines = content.split("\n")
    yaml_content = _extract_yaml_frontmatter(lines)

    if yaml_content:
        with contextlib.suppress(Exception):
            import yaml

            yaml_data = yaml.safe_load("\n".join(yaml_content))
            if isinstance(yaml_data, dict) and "description" in yaml_data:
                return yaml_data["description"]

    for raw_line in lines:
        line = raw_line.strip()
        if line and line != "---" and not line.startswith("#"):
            return line
    return ""


def _load_skill_entry(skill_dir: Path) -> dict[str, Any]:
    """Build one skill's catalog entry from its directory."""
    skill_id = skill_dir.name
    description = ""
    skill_md = skill_dir / "SKILL.md"
    if skill_md.exists():
        description = _parse_skill_description(skill_md.read_text(encoding="utf-8"))
    return {"id": skill_id, "name": skill_id, "description": description}


class AgentClient:
    """The TUI's one Arbora client: A2A for conversation, REST for the rest."""

    protocol = "a2a"

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        *,
        bearer_token: str | None = None,
    ) -> None:
        """Initialize the client.

        Args:
            base_url: The Arbora base URL.
            bearer_token: The caller's bearer credential. Remote Arbora
                endpoints require it for every A2A and gateway request.
        """
        if base_url != base_url.strip() or any(
            character.isspace()
            or ord(character) < 33
            or ord(character) == 127
            or character == "\\"
            for character in base_url
        ):
            raise ValueError("invalid Arbora endpoint")
        parsed = urlsplit(base_url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise ValueError("invalid Arbora endpoint")
        try:
            port = parsed.port
        except ValueError as exc:
            raise ValueError("invalid Arbora endpoint") from exc
        if port == 0:
            raise ValueError("invalid Arbora endpoint")
        is_loopback = parsed.hostname.lower().rstrip(".") in {
            "localhost",
            "127.0.0.1",
            "::1",
        }
        if parsed.scheme == "http" and not is_loopback:
            raise ValueError("remote Arbora endpoint requires TLS")
        if bearer_token is not None and (
            not bearer_token
            or any(
                character.isspace() or not 33 <= ord(character) <= 126
                for character in bearer_token
            )
        ):
            raise ValueError("invalid caller credential")
        if not is_loopback and bearer_token is None:
            raise ValueError("remote Arbora endpoint requires caller credential")
        self.base_url: str = base_url.rstrip("/")
        self.a2a_url = f"{self.base_url}{A2A_PATH}"
        self._has_caller_credential = bearer_token is not None
        headers = {"Authorization": f"Bearer {bearer_token}"} if bearer_token else None
        self._http_client = httpx.AsyncClient(timeout=30.0, headers=headers)
        self._current_session_id: str | None = None
        self._current_task_id: str | None = None
        self._pending_plans: dict[str, dict[str, Any]] = {}
        self._streaming: bool | None = None
        self.poll_interval = 0.5
        self.poll_timeout = 4 * 60 * 60

    @property
    def current_session_id(self) -> str | None:
        """Return the conversation (A2A context) most recently used."""
        return self._current_session_id

    @property
    def current_task_id(self) -> str | None:
        """Return the A2A task of the most recent turn, if any."""
        return self._current_task_id

    async def _rpc(
        self,
        method: str,
        params: dict[str, Any],
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """One unary JSON-RPC call; a JSON-RPC error raises."""
        response = await self._http_client.post(
            self.a2a_url,
            json={"jsonrpc": "2.0", "id": method, "method": method, "params": params},
            headers=headers,
        )
        frame = response.json()
        if not isinstance(frame, dict):
            response.raise_for_status()
            raise A2ATransportError({"message": "A2A response was not an object"})
        result = _frame_result(frame)
        response.raise_for_status()
        return result

    async def _rpc_stream(
        self,
        method: str,
        params: dict[str, Any],
        headers: dict[str, str] | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """One streaming JSON-RPC call; yields each event's ``result``."""
        body = {"jsonrpc": "2.0", "id": method, "method": method, "params": params}
        async with self._http_client.stream(
            "POST",
            self.a2a_url,
            json=body,
            headers={"Accept": "text/event-stream", **(headers or {})},
            timeout=None,
        ) as response:
            if response.status_code >= 400:
                await response.aread()
                frame = response.json()
                error = frame.get("error") if isinstance(frame, dict) else None
                raise A2ATransportError(
                    error if isinstance(error, dict) else {},
                    status_code=response.status_code,
                    acknowledged=isinstance(frame, dict) and "result" in frame,
                )
            pending: list[str] = []
            async for line in response.aiter_lines():
                if line:
                    pending.append(line)
                    continue
                for frame in _sse_frames(pending):
                    yield _frame_result(frame)
                pending = []
            for frame in _sse_frames(pending):
                yield _frame_result(frame)

    async def streaming_supported(self) -> bool:
        """Whether the served Agent Card allows ``message/stream``.

        An unreadable card keeps streaming, so a server that serves no card
        sees the original transport.
        """
        if self._streaming is None:
            card = await self.get_metadata()
            capabilities = card.get("capabilities") if isinstance(card, dict) else None
            self._streaming = not (
                isinstance(capabilities, dict)
                and capabilities.get("streaming") is False
            )
        return self._streaming

    async def _poll_results(
        self, message: dict[str, Any], headers: dict[str, str]
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Yield each bound unary snapshot, then its answer."""
        task = await self._rpc(
            "message/send",
            {"message": message, "configuration": {"blocking": False}},
            headers=headers,
        )
        binding = _poll_binding(task)
        supplied_context = message.get("contextId", "")
        # Arbora namespaces new contexts, but must preserve an owned canonical one.
        if (
            supplied_context.startswith("a2a-context-")
            and binding[1] != supplied_context
        ):
            raise A2ATransportError({"message": "Task correlation mismatch"})
        task_id = binding[0]
        deadline = asyncio.get_running_loop().time() + self.poll_timeout
        public_binding = None
        while True:
            if ("taskId" in task and task["taskId"] != task_id) or (
                public_binding is not None
                and not _public_run_metadata_matches(task, public_binding["run_id"])
            ):
                raise ValueError("A2A polled task binding changed")
            public_binding = public_binding or _public_run_binding(task)
            state = (task.get("status") or {}).get("state")
            if (
                state in _FINAL_STATES
                or state in {"input-required", "auth-required"}
                or not task_id
            ):
                break
            yield task
            remaining = deadline - asyncio.get_running_loop().time()
            try:
                async with asyncio.timeout(remaining):
                    await asyncio.sleep(self.poll_interval)
                    task = await self._rpc("tasks/get", {"id": task_id})
            except TimeoutError as exc:
                raise A2ATransportError(
                    {"message": "Polling timed out; remote outcome unknown"}
                ) from exc
            if _poll_binding(task) != binding:
                raise A2ATransportError({"message": "Task correlation mismatch"})
        if state == "completed":
            for artifact in _task_answers(task):
                yield {
                    "kind": "artifact-update",
                    "taskId": task_id,
                    "contextId": task.get("contextId"),
                    "artifact": artifact,
                }
        yield task

    async def _follow(
        self, method: str, params: dict[str, Any], session_id: str, headers: Any = None
    ) -> AsyncGenerator[dict[str, Any], None]:
        try:
            async for event in self._follow_results(
                self._rpc_stream(method, params, headers=headers),
                session_id,
                expected_task_id=params.get("id"),
            ):
                yield event
        except (A2ATransportError, httpx.HTTPError, ValueError):
            if identifier(params.get("id")):
                yield {
                    "type": "sideband",
                    "session_id": session_id,
                    "data": {"type": "public_details_unavailable"},
                    "public_run_invalid": {"task_id": params["id"]},
                }
            raise

    async def _follow_results(
        self,
        results: AsyncGenerator[dict[str, Any], None],
        session_id: str,
        *,
        expected_task_id: str | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        public_binding: dict[str, str] | None = None
        binding_invalid = False
        async for result in results:
            task_key = "id" if result.get("kind") == "task" else "taskId"
            if expected_task_id is not None and (
                result.get("kind") not in ("task", "status-update", "artifact-update")
                or result.get(task_key) != expected_task_id
                or any(
                    key in result and result[key] != expected_task_id
                    for key in ("id", "taskId")
                )
            ):
                raise ValueError("A2A task target mismatch")
            task_id = result.get("id") or result.get("taskId")
            if public_binding is not None:
                observed = {
                    "task_id": task_id,
                    "context_id": result.get("contextId"),
                    "run_id": _arbora_metadata(result).get("runId"),
                }
                if (
                    result.get("kind")
                    not in ("task", "status-update", "artifact-update")
                    or (
                        result.get("kind") in ("task", "status-update")
                        and _public_task_binding(result) is None
                    )
                    or not _public_run_metadata_matches(
                        result, public_binding["run_id"]
                    )
                    or result.get(task_key) != public_binding["task_id"]
                    or result.get("contextId") != public_binding["context_id"]
                    or any(
                        key in result and result[key] != public_binding["task_id"]
                        for key in ("id", "taskId")
                    )
                    or any(
                        value is not None and value != public_binding[key]
                        for key, value in observed.items()
                    )
                ):
                    binding_invalid = True
            elif not binding_invalid:
                public_binding = _public_run_binding(result)
            if task_id:
                self._current_task_id = str(task_id)
            self._remember_plan(result)
            normalized = normalize_a2a_event(result, session_id)
            if binding_invalid and not normalized:
                normalized = [
                    {"type": "sideband", "data": {}, "session_id": session_id}
                ]
            for event in normalized:
                if binding_invalid:
                    event.pop("public_run_binding", None)
                    event.pop("public_task_binding", None)
                    event["public_run_invalid"] = public_binding
                yield event
            status = result.get("status")
            if isinstance(status, dict) and status.get("state") == "input-required":
                plan = self._pending_plans.get(str(task_id))
                if plan is None:
                    yield {
                        "type": "error",
                        "message": (
                            "A2A approval requires a complete plan binding "
                            "or web console confirmation"
                        ),
                        "session_id": session_id,
                    }
                else:
                    yield {
                        "type": "tool_call",
                        "data": {
                            "call_id": str(task_id),
                            "name": str(plan["op"]),
                            "needs_approval": True,
                        },
                        "session_id": session_id,
                    }
                    yield {
                        "type": "turn_end",
                        "state": "input-required",
                        "session_id": session_id,
                    }

    def _remember_plan(self, result: dict[str, Any]) -> None:
        """Keep only a task's complete confirmation binding, never infer it."""
        task_id = result.get("id") or result.get("taskId")
        status = result.get("status")
        if not task_id or not isinstance(status, dict):
            return
        if status.get("state") != "input-required":
            self._pending_plans.pop(str(task_id), None)
            return
        self._pending_plans.pop(str(task_id), None)
        message = status.get("message")
        metadata = message.get("metadata") if isinstance(message, dict) else None
        plan = metadata.get("arboraPlan") if isinstance(metadata, dict) else None
        if (
            isinstance(plan, dict)
            and isinstance(plan.get("plan_ref"), str)
            and isinstance(plan.get("op"), str)
            and isinstance(plan.get("params"), dict)
            and plan.get("confirm") == "plan"
            and not _is_approval_operation(plan["op"])
        ):
            self._pending_plans[str(task_id)] = plan

    async def invoke_op(
        self,
        op: str,
        params: dict[str, Any],
        *,
        plan_ref: str | None = None,
        idempotency_key: str | None = None,
    ) -> Any:
        """Call one versioned operation using the shared Arbora envelope."""
        if (
            not isinstance(op, str)
            or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", op) is None
            or ".." in op
            or not isinstance(params, dict)
        ):
            raise ValueError("operation id and object params are required")
        if _is_approval_operation(op):
            raise ArboraOperationError("APPROVAL_UNAVAILABLE")
        if sys.version_info < (3, 12):  # noqa: UP036 - TUI-RUNTIME-R001.6 refusal
            raise ArboraOperationError("CLIENT_UNAVAILABLE")
        try:
            from arbora.client._generated_models import schema_for
            from arbora.client.invoke import invoke
        except ImportError as exc:
            raise ArboraOperationError("CLIENT_UNAVAILABLE") from exc
        try:
            schema_for(op)
        except KeyError as exc:
            raise ArboraOperationError("UNKNOWN_OP") from exc
        except FileNotFoundError as exc:
            raise ArboraOperationError("CLIENT_UNAVAILABLE") from exc
        except RuntimeError as exc:
            raise ArboraOperationError("REGISTRY_MISMATCH") from exc
        headers = {"Idempotency-Key": idempotency_key or uuid.uuid4().hex}
        if plan_ref:
            headers["Arbora-Plan-Ref"] = plan_ref
        try:
            payload = await invoke(_OperationTransport(self, headers), op, params)
        except RuntimeError as exc:
            if str(exc) != "Arbora registry digest mismatch":
                raise
            raise ArboraOperationError("REGISTRY_MISMATCH") from exc
        if not payload["ok"]:
            error = payload.get("error")
            code = error.get("code") if isinstance(error, dict) else None
            details = error.get("details") if isinstance(error, dict) else None
            raise ArboraOperationError(
                code if isinstance(code, str) else "UNKNOWN",
                details if isinstance(details, dict) else None,
            )
        if "result" not in payload:
            raise ArboraOperationError("INVALID_ENVELOPE")
        return payload.get("result")

    async def get_current_plan(self, run_id: str) -> dict[str, Any]:
        """Read one explicit run's current plan through the public operation client."""
        if not isinstance(run_id, str) or not run_id.strip() or len(run_id) > 512:
            raise ValueError("an explicit run ID is required")
        result = await self.invoke_op("runs.current_plan", {"run_id": run_id})
        if not isinstance(result, dict) or not isinstance(result.get("value"), dict):
            raise ArboraOperationError("INVALID_ENVELOPE")
        return result["value"]

    async def get_public_run_events(
        self, run_id: str, *, task_id: str, after: int = 0
    ) -> dict[str, Any]:
        """Read only the registered, caller-authorized public event projection."""
        if (
            not identifier(run_id)
            or not identifier(task_id)
            or type(after) is not int
            or not 0 <= after <= MAX_SEQUENCE
        ):
            raise ValueError("invalid public run cursor")
        result = await self.invoke_op(
            "runs.events",
            {"run_id": run_id, "task_id": task_id, "after": after, "limit": 1000},
        )
        if not isinstance(result, dict) or not isinstance(result.get("value"), dict):
            raise ArboraOperationError("INVALID_ENVELOPE")
        return result["value"]

    async def confirm_plan(
        self,
        *,
        plan_ref: str,
        op: str,
        params: dict[str, Any],
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """Refuse confirmation until the signed pending-call exchange is available."""
        if not plan_ref or not op or not isinstance(params, dict):
            raise ValueError("complete plan binding is required")
        if _is_approval_operation(op):
            raise ArboraOperationError("APPROVAL_UNAVAILABLE")
        if not self._has_caller_credential:
            raise ArboraOperationError("CALLER_CREDENTIAL_REQUIRED")
        raise ArboraOperationError("APPROVAL_UNAVAILABLE")

    async def stream(
        self,
        query: str,
        session_id: str | None = None,
        parts: list[dict[str, Any]] | None = None,
        mode_id: str | None = None,
        model: str | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Run one conversation turn as a streamed A2A task.

        ``mode_id`` selects the typed task Arbora routes on
        (:data:`MODE_TASK_IRIS`; unknown modes use ``ask``); routing then selects
        the authorized agent. ``model`` is not part of the A2A contract and is
        not sent. Only text parts are carried.

        Yields:
            Normalized event dictionaries, starting with ``session_started``.
        """
        session_id = session_id or new_session_id()
        self._current_session_id = session_id
        self._current_task_id = None
        yield {"type": "session_started", "session_id": session_id}
        if any(
            not isinstance(part, dict)
            or set(part) - {"type", "text"}
            or part.get("type", "text") != "text"
            or not isinstance(part.get("text"), str)
            for part in parts or []
        ):
            yield {
                "type": "error",
                "message": "only text parts are supported by the Arbora A2A transport",
                "session_id": session_id,
            }
            return
        texts = [query, *((part or {}).get("text", "") for part in parts or [])]
        message = {
            "kind": "message",
            "role": "user",
            "parts": [{"kind": "text", "text": text} for text in texts if text],
            "messageId": uuid.uuid4().hex,
            "contextId": session_id,
            "metadata": {
                "arboraTaskIris": [
                    MODE_TASK_IRIS.get(mode_id or "ask", MODE_TASK_IRIS["ask"])
                ]
            },
        }
        headers = {"Idempotency-Key": uuid.uuid4().hex}
        public_binding = None
        try:
            async for event in self._follow_results(
                self._conversation_results(message, headers), session_id
            ):
                if "public_run_binding" in event:
                    public_binding = event["public_run_binding"]
                yield event
        except (A2ATransportError, httpx.HTTPError, ValueError) as exc:
            logger.warning("A2A stream failed: %s", exc)
            error: dict[str, Any] = {
                "type": "error",
                "message": str(exc),
                "session_id": session_id,
            }
            if public_binding is not None:
                error["public_run_invalid"] = public_binding
            yield error

    async def _conversation_results(
        self, message: dict[str, Any], headers: dict[str, str]
    ) -> AsyncGenerator[dict[str, Any], None]:
        acknowledged = False
        if await self.streaming_supported():
            try:
                async for result in self._rpc_stream(
                    "message/stream", {"message": message}, headers=headers
                ):
                    # Even a result that renders nothing may acknowledge admission.
                    acknowledged = True
                    yield result
                return
            except A2ATransportError as exc:
                if (
                    acknowledged
                    or exc.acknowledged
                    or type(exc.code) is not int
                    or exc.status_code in {401, 403}
                    or exc.code not in _STREAM_UNSUPPORTED
                ):
                    raise
                self._streaming = False
        async for result in self._poll_results(message, headers):
            yield result

    async def resubscribe(
        self, task_id: str, *, last_event_id: str | None = None
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Re-attach to a task's stream after a disconnect.

        ``POST /a2a`` ``tasks/resubscribe``; ``last_event_id`` skips the state
        the client already rendered.
        """
        session_id = self._current_session_id or new_session_id()
        headers = {"Last-Event-ID": last_event_id} if last_event_id else None
        async for event in self._follow(
            "tasks/resubscribe", {"id": task_id}, session_id, headers=headers
        ):
            yield event

    async def cancel_task(self, task_id: str | None = None) -> dict[str, Any]:
        """Cancel a task, the current turn's by default.

        ``POST /a2a`` ``tasks/cancel``; returns the cancelled task.
        """
        target = task_id or self._current_task_id
        if not target:
            raise ValueError("no A2A task to cancel")
        return await self._rpc("tasks/cancel", {"id": target})

    async def get_task(self, task_id: str) -> dict[str, Any]:
        """Read one owned task (``POST /a2a`` ``tasks/get``)."""
        return await self._rpc("tasks/get", {"id": task_id})

    async def send_decision(
        self,
        decisions: dict[str, str],
        feedback: str | None = None,
        session_id: str | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Confirm only a bound PLAN request; console plans stay in the browser."""
        current_session = session_id or self._current_session_id
        for task_id, decision in decisions.items():
            if decision == "reject":
                try:
                    await self.cancel_task(task_id)
                except (A2ATransportError, httpx.HTTPError, ValueError) as exc:
                    yield {
                        "type": "error",
                        "message": str(exc),
                        "session_id": current_session,
                    }
                    return
                self._pending_plans.pop(task_id, None)
                yield {
                    "type": "turn_end",
                    "state": "canceled",
                    "session_id": current_session,
                }
                continue
            plan = self._pending_plans.get(task_id)
            if decision != "accept" or plan is None:
                yield {
                    "type": "error",
                    "message": "plan requires a valid A2A confirmation binding",
                    "session_id": current_session,
                }
                return
            try:
                await self.confirm_plan(
                    plan_ref=plan["plan_ref"], op=plan["op"], params=plan["params"]
                )
            except (
                A2ATransportError,
                ArboraOperationError,
                httpx.HTTPError,
                ValueError,
            ) as exc:
                yield {
                    "type": "error",
                    "message": str(exc),
                    "session_id": current_session,
                }
                return
            self._pending_plans.pop(task_id, None)
            if current_session:
                async for event in self.resubscribe(task_id):
                    yield event

    async def submit_extraction(
        self, *, text: str = "", url: str = "", rounds: int = 1, dedup: bool = True
    ) -> dict[str, Any]:
        """Submit a document fact-extraction job to the gateway (ECO-4.43)."""
        resp = await self._http_client.post(
            f"{self.base_url}/api/enhanced/extract/submit",
            json={"text": text, "url": url, "rounds": rounds, "dedup": dedup},
        )
        resp.raise_for_status()
        return resp.json()

    async def stream_extraction(
        self, job_id: str
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Stream a job's extraction events (round_start|fact|…|job_done)."""
        async with self._http_client.stream(
            "GET",
            f"{self.base_url}/api/enhanced/extract/stream/{job_id}",
            timeout=None,
        ) as stream:
            async for line in stream.aiter_lines():
                if line.startswith("data: "):
                    try:
                        yield json.loads(line[6:])
                    except json.JSONDecodeError:
                        continue

    async def extraction_jsonl(self, job_id: str) -> str:
        """Fetch a job's facts as JSONL text (upstream parity)."""
        resp = await self._http_client.get(
            f"{self.base_url}/api/enhanced/extract/jsonl/{job_id}"
        )
        resp.raise_for_status()
        return resp.text

    async def get_metadata(self) -> dict[str, Any]:
        """Fetch the Arbora Agent Card for the ``/a2a`` endpoint.

        ``GET /.well-known/agent-card.json``.
        """
        try:
            response = await self._http_client.get(f"{self.base_url}{AGENT_CARD_PATH}")
            if response.status_code in {404, 405}:
                response = await self._http_client.get(
                    f"{self.a2a_url}{AGENT_CARD_PATH}"
                )
            if response.status_code != 200:
                return {}
            card = response.json()
            return card if isinstance(card, dict) else {}
        except (httpx.HTTPError, ValueError):
            return {}

    @staticmethod
    def _gateway_body(response: httpx.Response) -> Any:
        """Return a direct FastAPI body or unwrap the shared HTTP envelope."""
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict) and "status_code" in payload and "data" in payload:
            return payload["data"]
        return payload

    async def list_capabilities(
        self,
        *,
        query: str | None = None,
        status: str | None = None,
        intent: str | None = None,
        tag: str | None = None,
        include_actions: bool = True,
    ) -> CapabilityCatalog:
        """Fetch the live catalog used by schema-driven frontend surfaces."""
        params = {
            key: value
            for key, value in {
                "q": query,
                "status": status,
                "intent": intent,
                "tag": tag,
                "include_actions": str(include_actions).lower(),
            }.items()
            if value is not None
        }
        response = await self._http_client.get(
            f"{self.base_url}/api/capabilities", params=params
        )
        return CapabilityCatalog.from_payload(self._gateway_body(response))

    async def get_capability(self, capability_id: str) -> CapabilityDescriptor:
        """Fetch one live capability descriptor by stable ID."""
        encoded = quote(capability_id, safe="")
        response = await self._http_client.get(
            f"{self.base_url}/api/capabilities/{encoded}"
        )
        return CapabilityDescriptor.from_payload(self._gateway_body(response))

    async def preflight_capability(
        self,
        capability_id: str,
        *,
        action: str | None = None,
        inputs: dict[str, Any] | None = None,
        target: str | None = None,
    ) -> CapabilityPreflight:
        """Validate inputs and preview availability/policy without executing."""
        encoded = quote(capability_id, safe="")
        response = await self._http_client.post(
            f"{self.base_url}/api/capabilities/{encoded}/preflight",
            json={
                "action": action,
                "inputs": inputs or {},
                "target": target,
            },
        )
        return CapabilityPreflight.from_payload(self._gateway_body(response))

    async def invoke_capability(
        self,
        capability_id: str,
        inputs: dict[str, Any],
        *,
        action: str,
        target: str | None = None,
        approval_id: str | None = None,
        run_id: str | None = None,
        session_id: str | None = None,
    ) -> CapabilityInvocation:
        """Execute or resume through the gateway-owned governance boundary."""
        if approval_id is not None:
            raise ArboraOperationError("APPROVAL_UNAVAILABLE")
        encoded = quote(capability_id, safe="")
        payload: dict[str, Any] = {"action": action, "inputs": inputs}
        payload.update(
            {
                key: value
                for key, value in {
                    "target": target,
                    "approval_id": approval_id,
                    "run_id": run_id,
                    "session_id": session_id,
                }.items()
                if value is not None
            }
        )
        response = await self._http_client.post(
            f"{self.base_url}/api/capabilities/{encoded}/invoke", json=payload
        )
        result = self._gateway_body(response)
        return CapabilityInvocation.from_payload(
            capability_id,
            result,
            http_status=response.status_code,
            requested_session_id=session_id,
        )

    async def get_run_summary(self, run_id: str) -> RunSummary:
        """Fetch a summary for one replayable canonical run."""
        encoded = quote(run_id, safe="")
        response = await self._http_client.get(f"{self.base_url}/api/runs/{encoded}")
        return RunSummary.from_payload(self._gateway_body(response))

    async def list_runs(
        self,
        *,
        session_id: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> RunCatalog:
        """List newest-first canonical run lifecycle summaries."""
        params = {
            key: value
            for key, value in {
                "session_id": session_id,
                "status": status,
                "limit": limit,
            }.items()
            if value is not None
        }
        response = await self._http_client.get(
            f"{self.base_url}/api/runs", params=params
        )
        return RunCatalog.from_payload(self._gateway_body(response))

    async def get_run_events(
        self, run_id: str, *, after: int = 0, limit: int = 1_000
    ) -> RunEventPage:
        """Replay canonical run events after a per-run sequence cursor."""
        encoded = quote(run_id, safe="")
        response = await self._http_client.get(
            f"{self.base_url}/api/runs/{encoded}/events",
            params={"after": after, "limit": limit},
        )
        payload = self._gateway_body(response)
        if isinstance(payload, dict) and payload.get("schema_version") == SCHEMA:
            raise ValueError(
                "Public replay requires inline task details; "
                "Mission Control uses the legacy schema"
            )
        return RunEventPage.from_payload(payload)

    async def get_event_schema(self) -> dict[str, Any]:
        """Fetch the versioned canonical run-event JSON Schema."""
        response = await self._http_client.get(f"{self.base_url}/api/events/schema")
        payload = self._gateway_body(response)
        return payload if isinstance(payload, dict) else {}

    async def list_configured_models(self) -> dict[str, Any]:
        """Read legacy registry metadata without masking failed reads as empty.

        This is not models.list admission or server-side model selection.
        HTTP errors and invalid registry shapes propagate to the command view.
        """
        response = await self._http_client.get(f"{self.base_url}/models")
        response.raise_for_status()
        data = response.json()
        if (
            not isinstance(data, dict)
            or not isinstance(data.get("models"), list)
            or any(
                not isinstance(model, dict) or not isinstance(model.get("id"), str)
                for model in data["models"]
            )
            or not isinstance(data.get("default_id"), (str, type(None)))
        ):
            raise ValueError("Invalid model registry")
        for model in data["models"]:
            tags = model.get("tags")
            if tags is not None and (
                not isinstance(tags, list)
                or any(not isinstance(tag, str) for tag in tags)
            ):
                raise ValueError("Invalid model tags")
            cost = model.get("cost")
            if cost is None:
                continue
            if not isinstance(cost, dict):
                raise ValueError("Invalid model cost")
            for key in ("input", "output"):
                value = cost.get(key, 0)
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise ValueError("Invalid model cost")
                try:
                    finite = math.isfinite(float(value))
                except OverflowError as exc:
                    raise ValueError("Invalid model cost") from exc
                if not finite:
                    raise ValueError("Invalid model cost")
        return data

    async def list_tools(self) -> list[dict[str, Any]]:
        """Fetch the loaded skills and tools from the backend Knowledge Graph.

        Hits the core ``GET /tools`` endpoint exposed by ``agent_utilities.server``.
        Returns a list of dicts representing Tool and Skill nodes.
        """
        try:
            response = await self._http_client.get(f"{self.base_url}/tools")
            response.raise_for_status()
            data = response.json()
            if isinstance(data, list):
                return data
            return []
        except Exception as e:
            logger.error(f"Failed to fetch tools registry: {e}")
            return []

    async def _obs_get(self, path: str, params: dict | None = None) -> Any:
        """GET an /api/observability/* endpoint.

        CONCEPT:AU-ECO.mcp.usage-cost-observability-surface
        """
        try:
            response = await self._http_client.get(
                f"{self.base_url}/api/observability{path}",
                params={k: v for k, v in (params or {}).items() if v},
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.debug(f"observability {path} failed: {e}")
            return None

    async def get_usage_summary(self) -> dict[str, Any]:
        """Read the caller tenant snapshot without inventing absent metrics."""
        return await self._read_operation_value("usage.read", {})

    async def get_usage_by_model(self, **f: Any) -> list[dict[str, Any]]:
        return await self._obs_get("/by-model", f) or []

    async def get_usage_tools(self, **f: Any) -> list[dict[str, Any]]:
        return await self._obs_get("/analytics/tools", f) or []

    async def get_usage_activity(self, **f: Any) -> list[dict[str, Any]]:
        return await self._obs_get("/analytics/activity", f) or []

    async def get_usage_top_sessions(
        self, *, limit: int = 20, **f: Any
    ) -> list[dict[str, Any]]:
        return await self._obs_get("/top-sessions", {"limit": limit, **f}) or []

    async def get_usage_traces(self) -> dict[str, Any]:
        return await self._obs_get("/traces") or {"enabled": False, "traces": []}

    async def list_history_tasks(self, cursor: str | None = None) -> dict[str, Any]:
        """Read one caller-scoped tasks/list page through POST /a2a."""
        params: dict[str, Any] = {"limit": 50}
        if cursor is not None:
            params["cursor"] = cursor
        page = await self._rpc("tasks/list", params)
        tasks = page.get("tasks")
        continuation = page.get("nextCursor")
        if not isinstance(tasks, list) or len(tasks) > 50:
            raise ValueError("Invalid task history page")
        if continuation is not None and (
            not isinstance(continuation, str)
            or not continuation
            or continuation == cursor
        ):
            raise ValueError("Invalid task history cursor")
        for task in tasks:
            self._validate_history_task(task)
        if len({task["id"] for task in tasks}) != len(tasks):
            raise ValueError("Duplicate task history identity")
        return page

    @staticmethod
    def _validate_history_task(task: Any) -> None:
        if not isinstance(task, dict) or any(
            not isinstance(task.get(key), str) or not task[key].strip()
            for key in ("id", "contextId")
        ):
            raise ValueError("Invalid task history identity")
        if not isinstance(task.get("status"), dict) or not isinstance(
            task["status"].get("state"), str
        ):
            raise ValueError("Invalid task history status")

    async def get_history_task(self, task_id: str, context_id: str) -> dict[str, Any]:
        """Read tasks/get through POST /a2a without changing conversations."""
        task = await self._rpc("tasks/get", {"id": task_id})
        self._validate_history_task(task)
        if task["id"] != task_id or task["contextId"] != context_id:
            raise ValueError("Task history identity changed")
        return task

    async def _read_operation_value(
        self, op: str, params: dict[str, Any]
    ) -> dict[str, Any]:
        result = await self.invoke_op(op, params)
        if not isinstance(result, dict) or not isinstance(result.get("value"), dict):
            raise ArboraOperationError("INVALID_ENVELOPE")
        return result["value"]

    async def get_mcp_config(self) -> dict[str, Any]:
        """Read caller-visible fleet status without inferring configuration."""
        value = await self._read_operation_value("fleet.status", {})
        if not isinstance(value.get("children"), dict):
            raise ArboraOperationError("INVALID_ENVELOPE")
        return value

    async def list_mcp_tools(self) -> list[dict[str, Any]]:
        """Read at most ten catalog pages; never return an incomplete list."""
        items: list[dict[str, Any]] = []
        cursor: str | None = None
        seen: set[str] = set()
        for _ in range(10):
            params: dict[str, Any] = {"browse": True, "kinds": ["tool"], "limit": 100}
            if cursor is not None:
                params["cursor"] = cursor
            value = await self._read_operation_value("fleet.catalog.list", params)
            page = value.get("items")
            if (
                not isinstance(page, list)
                or len(page) > 100
                or any(
                    not isinstance(item, dict)
                    or any(
                        not isinstance(item.get(key), str)
                        for key in ("id", "name", "description")
                    )
                    for item in page
                )
            ):
                raise ArboraOperationError("INVALID_ENVELOPE")
            items.extend(page)
            if "next_cursor" not in value:
                raise ArboraOperationError("INVALID_ENVELOPE")
            cursor = value["next_cursor"]
            if cursor is None:
                return items
            if (
                not isinstance(cursor, str)
                or not cursor
                or len(cursor) > 1024
                or cursor in seen
            ):
                raise ArboraOperationError("INVALID_ENVELOPE")
            seen.add(cursor)
        raise ArboraOperationError("CATALOG_PAGE_LIMIT")

    async def list_skills(self) -> list[dict[str, Any]]:
        """Fetch available skills from the backend or filesystem."""
        try:
            # Try to use the helper function from agent-utilities
            logger.info(
                f"Fetching skills from {self.base_url}/api/enhanced/helpers/list_skills"
            )
            response = await self._http_client.post(
                f"{self.base_url}/api/enhanced/helpers/list_skills", json={}
            )
            response.raise_for_status()
            result = response.json()
            logger.info(f"Skills response: {result}")
            # The helper returns the result directly
            if isinstance(result, list):
                return result
            elif isinstance(result, dict) and "result" in result:
                return result["result"]
            return []
        except Exception as e:
            logger.error(f"Failed to fetch skills from backend: {e}")
            # Fallback: try to load skills from universal-skills directory
            return await self._load_skills_from_filesystem()

    async def _load_skills_from_filesystem(self) -> list[dict[str, Any]]:
        """Load skills from the universal-skills directory as a fallback."""
        try:
            # Need to go up to Workspace level
            workspace_root = Path(__file__).parent.parent.parent.parent
            skills_dirs = _candidate_skills_dirs(workspace_root)

            skills_dir = None
            for dir_path in skills_dirs:
                if dir_path.exists() and dir_path.is_dir():
                    skills_dir = dir_path
                    logger.info(f"Found skills directory: {skills_dir}")
                    break

            if not skills_dir:
                logger.warning(
                    f"Could not find universal-skills directory in {skills_dirs}"
                )
                logger.warning(f"Workspace root: {workspace_root}")
                return []

            skills = [
                _load_skill_entry(skill_dir)
                for skill_dir in skills_dir.iterdir()
                if skill_dir.is_dir()
            ]

            logger.info(f"Loaded {len(skills)} skills from filesystem")
            return skills
        except Exception as e:
            logger.error(f"Failed to load skills from filesystem: {e}")
            return []

    async def get_graph_stats(self) -> dict[str, Any]:
        """Fetch aggregate statistics for the knowledge graph.

        Returns:
            Dictionary with totals and by-type breakdowns.
        """
        response = await self._http_client.get(
            f"{self.base_url}/api/enhanced/graph/stats"
        )
        response.raise_for_status()
        return response.json()

    async def get_fleet_topology(self) -> dict[str, Any]:
        """Fetch the fleet worker and placement topology (OS-5.10).

        Returns:
            Dictionary describing fleet workers and their placement.
        """
        response = await self._http_client.get(f"{self.base_url}/api/fleet/topology")
        response.raise_for_status()
        return response.json()

    async def get_fleet_approvals(self) -> list[dict[str, Any]]:
        """Fetch pending ActionPolicy approvals awaiting a decision (OS-5.24).

        Returns:
            List of pending approval dictionaries.
        """
        response = await self._http_client.get(f"{self.base_url}/api/fleet/approvals")
        response.raise_for_status()
        data = response.json()
        if isinstance(data, dict):
            # The gateway contract names this collection ``pending``. Keep the
            # legacy envelope as a read-only fallback for older deployments.
            pending = data.get("pending", data.get("approvals", []))
            return pending if isinstance(pending, list) else []
        return data if isinstance(data, list) else []

    async def grant_fleet_approval(
        self, job_id: str, decision: str = "approved"
    ) -> dict[str, Any]:
        """Refuse legacy fleet grants until durable EH-590 authority is served."""
        if decision not in {"approved", "denied"}:
            msg = "decision must be 'approved' or 'denied'"
            raise ValueError(msg)
        raise ArboraOperationError("APPROVAL_UNAVAILABLE")

    async def list_graph_nodes(
        self, node_type: str | None = None
    ) -> list[dict[str, Any]]:
        """List graph nodes, optionally filtered by type.

        Args:
            node_type: Optional node type to filter on (e.g. ``File``, ``Symbol``).

        Returns:
            List of node dictionaries.
        """
        params: dict[str, str] = {}
        if node_type:
            params["node_type"] = node_type
        response = await self._http_client.get(
            f"{self.base_url}/api/enhanced/graph/nodes", params=params
        )
        response.raise_for_status()
        return response.json()

    async def list_graph_relationships(self, limit: int = 100) -> list[dict[str, Any]]:
        """List graph relationships up to ``limit`` entries.

        Args:
            limit: Maximum number of relationships to return.

        Returns:
            List of relationship dictionaries.
        """
        response = await self._http_client.get(
            f"{self.base_url}/api/enhanced/graph/relationships",
            params={"limit": limit},
        )
        response.raise_for_status()
        return response.json()

    async def search_graph(self, query: str, top_k: int = 10) -> list[dict[str, Any]]:
        """Hybrid search across graph nodes.

        Args:
            query: Free-text search query.
            top_k: Maximum number of hits to return.

        Returns:
            List of search-hit dictionaries.
        """
        response = await self._http_client.get(
            f"{self.base_url}/api/enhanced/graph/search",
            params={"query": query, "top_k": top_k},
        )
        response.raise_for_status()
        return response.json()

    async def query_graph_as_of(self, query: str) -> list[dict[str, Any]]:
        """Execute a (UQL) graph query verbatim, returning result rows.

        Thin pass-through to ``POST /api/enhanced/graph/query`` used by the
        temporal scrubber, which pins the query to an instant with the engine's
        ``|> AS OF @<unix-seconds>`` bi-temporal stage (KG-2.250) client-side.
        The backend passes the query through to the engine unchanged.

        Args:
            query: The full UQL query string (already carrying any AS OF stage).

        Returns:
            List of result-row dictionaries.
        """
        response = await self._http_client.post(
            f"{self.base_url}/api/enhanced/graph/query",
            json={"query": query},
        )
        response.raise_for_status()
        return response.json()

    async def get_graph_impact(self, symbol: str) -> list[dict[str, Any]]:
        """Return the topological impact set for ``symbol``.

        Args:
            symbol: Fully-qualified symbol name (e.g. ``module.Class.method``).

        Returns:
            List of impacted node dictionaries.
        """
        response = await self._http_client.get(
            f"{self.base_url}/api/enhanced/graph/impact/{symbol}"
        )
        response.raise_for_status()
        return response.json()

    async def get_impact(self, symbol: str) -> list[dict[str, Any]]:
        """Return impact-analysis results for ``symbol``.

        Alias of :meth:`get_graph_impact` that matches the parity audit naming.

        Args:
            symbol: Fully-qualified symbol name.

        Returns:
            List of impacted node dictionaries.
        """
        return await self.get_graph_impact(symbol)

    async def _graph_post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        """POST to a gateway ``/graph/*`` engine-surface route and unwrap it.

        The action-routed twins in :data:`ACTION_TOOL_ROUTES` (KG-2.310)
        respond with ``{"status": "success", "result": <tool-json>}``; this
        helper returns the inner ``result`` object. Tool-level failures degrade
        cleanly into ``result`` as ``{"error": "..."}`` (HTTP 200), while
        transport/gateway failures raise ``httpx.HTTPStatusError`` for the
        caller to render.

        The gateway mounts the whole canonical KG route table under ``/api``
        (``register_graph_routes(app, prefix="/api")``), so the request URL is
        ``{base_url}/api{path}``. Posting to the bare ``{base_url}{path}`` — as
        this helper used to — reached nothing: every engine-surface command
        (``/ask``, ``/nl``, ``/obs``, ``/broker``, ``/kvcache``) 404'd.

        Args:
            path: A ``/graph/*`` route path (e.g. ``/graph/promql``).
            payload: The tool keyword arguments to send as the JSON body.

        Returns:
            The unwrapped ``result`` object (empty dict when absent).
        """
        response = await self._http_client.post(
            f"{self.base_url}{GATEWAY_API_PREFIX}{path}", json=payload
        )
        response.raise_for_status()
        data = response.json()
        if isinstance(data, dict):
            result = data.get("result", data)
            return result if isinstance(result, dict) else {"result": result}
        return {}

    async def graph_nl_query(
        self,
        text: str,
        *,
        dialect: str = "auto",
        execute: bool = True,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Translate a natural-language request into a query (KG-2.305).

        Hits ``POST /graph/nl-query``; the AU fleet LLM plans a single
        read-only query (UQL/cypher/sql/sparql), which the engine executes.

        Returns:
            The tool payload: generated ``query``, ``rows``/``result``,
            ``citations``, or ``error``.
        """
        return await self._graph_post(
            "/graph/nl-query",
            {
                "text": text,
                "dialect": dialect,
                "execute": execute,
                "limit": limit,
            },
        )

    async def graph_ask_data(
        self,
        question: str,
        *,
        dialect: str = "auto",
        max_corrections: int = 2,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Answer a data question with the multi-step analyst loop (KG-2.308).

        Hits ``POST /graph/ask-data``; a bounded ReAct agent schema-links,
        plans, executes, self-corrects, then synthesizes a NL answer.

        Returns:
            The tool payload: synthesized ``answer``, ``query``, result rows,
            ``citations``, ``schema``, attempt trace, or ``error``.
        """
        return await self._graph_post(
            "/graph/ask-data",
            {
                "question": question,
                "dialect": dialect,
                "max_corrections": max_corrections,
                "limit": limit,
            },
        )

    async def graph_promql(
        self,
        query: str,
        *,
        action: str = "instant",
        time: str = "",
        start: str = "",
        end: str = "",
        step: str = "",
    ) -> dict[str, Any]:
        """Query engine observability metrics with PromQL (KG-2.310).

        Hits ``POST /graph/promql``; ``action='instant'`` evaluates once,
        ``action='range'`` evaluates over ``start..end`` at ``step``.

        Returns:
            The tool payload (metric samples under ``result``) or ``error``.
        """
        payload: dict[str, Any] = {"query": query, "action": action}
        for key, value in (
            ("time", time),
            ("start", start),
            ("end", end),
            ("step", step),
        ):
            if value:
                payload[key] = value
        return await self._graph_post("/graph/promql", payload)

    async def graph_traces(
        self,
        *,
        action: str = "search",
        trace_id: str = "",
        service: str = "",
        operation: str = "",
        query: str = "",
        limit: int = 20,
    ) -> dict[str, Any]:
        """Search or fetch distributed traces (KG-2.310).

        Hits ``POST /graph/traces``; ``action='search'`` filters by
        ``service``/``operation``/``query``, ``action='get'`` fetches one
        ``trace_id``.

        Returns:
            The tool payload (matched traces under ``result``) or ``error``.
        """
        payload: dict[str, Any] = {"action": action, "limit": limit}
        for key, value in (
            ("trace_id", trace_id),
            ("service", service),
            ("operation", operation),
            ("query", query),
        ):
            if value:
                payload[key] = value
        return await self._graph_post("/graph/traces", payload)

    async def graph_broker(
        self, *, action: str = "stats", params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Inspect the engine message broker (KG-2.310).

        Hits ``POST /graph/broker``; ``action`` is a broker method such as
        ``stats``, ``list_queues``, or ``list_exchanges``. Extra keyword
        arguments are forwarded via ``params_json``.

        Returns:
            The tool payload (broker stats/listing under ``result``) or
            ``error``.
        """
        payload: dict[str, Any] = {"action": action}
        if params:
            payload["params_json"] = json.dumps(params)
        return await self._graph_post("/graph/broker", payload)

    async def graph_kvcache(self, *, action: str = "stats") -> dict[str, Any]:
        """Read shared content-addressed KV-cache stats (KG-2.306/2.310).

        Hits ``POST /graph/kvcache``; ``action='stats'`` returns occupancy and
        dedup counters.

        Returns:
            The tool payload (cache stats under ``result``) or ``error``.
        """
        return await self._graph_post("/graph/kvcache", {"action": action})

    async def reload_mcp(self) -> dict[str, Any]:
        """Hot-reload the backend MCP configuration.

        Returns:
            Dictionary with ``status`` and reload details
            (e.g. ``{"status": "reloaded", "agents": N, "tools": M}``).
        """
        response = await self._http_client.post(f"{self.base_url}/mcp/reload")
        response.raise_for_status()
        return response.json()

    async def aclose(self) -> None:
        """Close the underlying HTTP client and release its connections."""
        await self._http_client.aclose()

    async def get_dashboard_full(self) -> dict[str, Any]:
        """Fetch the service dashboard layout and widget data in one request.

        Returns:
            ``{"layout": {...}, "data": {service_id: {...}}}`` from the backend
            gateway's ``/api/dashboard/full`` endpoint. Fetching over HTTP keeps
            the frontend free of the heavy ``agent_utilities`` gateway package.
        """
        response = await self._http_client.get(f"{self.base_url}/api/dashboard/full")
        response.raise_for_status()
        return response.json()

    async def get_dashboard_data(self) -> dict[str, Any]:
        """Fetch current widget data for all configured dashboard services.

        Returns:
            Mapping of ``service_id`` to its widget-data dictionary.
        """
        response = await self._http_client.get(f"{self.base_url}/api/dashboard/data")
        response.raise_for_status()
        return response.json()

    async def generate_codemap(self, prompt: str) -> dict[str, Any]:
        """Generate a codebase codemap artifact for ``prompt``.

        Args:
            prompt: Free-form description of the target code region.

        Returns:
            Dictionary with ``status``, ``codemap_id``, and an ``artifact``
            payload containing ``mermaid`` and/or ``markdown`` renders.
        """
        response = await self._http_client.post(
            f"{self.base_url}/api/codemap", json={"prompt": prompt}
        )
        response.raise_for_status()
        return response.json()

    async def list_resources(self) -> list[dict[str, Any]]:
        """List callable resources exposed by the backend.

        Returns:
            List of resource dictionaries (type, name, description, ...).
        """
        response = await self._http_client.get(
            f"{self.base_url}/api/enhanced/resources"
        )
        response.raise_for_status()
        return response.json()

    async def spawn_resource(self, spec: dict[str, Any]) -> dict[str, Any]:
        """Spawn a specialized agent from ``spec``.

        Args:
            spec: Specialized-agent payload forwarded to the backend verbatim.

        Returns:
            The spawned-agent descriptor returned by the server.
        """
        response = await self._http_client.post(
            f"{self.base_url}/api/enhanced/resources/spawn", json=spec
        )
        response.raise_for_status()
        return response.json()

    async def get_pipeline_status(self) -> dict[str, Any]:
        """Fetch the current 12-phase ingestion pipeline status.

        Returns:
            Dictionary with ``status`` and per-phase details under ``phases``.
        """
        response = await self._http_client.get(
            f"{self.base_url}/api/enhanced/pipeline/status"
        )
        response.raise_for_status()
        return response.json()

    async def trigger_pipeline(self, phase: str | None = None) -> dict[str, Any]:
        """Trigger a pipeline run for ``phase`` or the full pipeline.

        Args:
            phase: Optional phase name (e.g. ``"scan"``, ``"embedding"``).

        Returns:
            Dictionary containing ``status`` and trigger metadata.
        """
        payload: dict[str, Any] = {}
        if phase:
            payload["phase"] = phase
        response = await self._http_client.post(
            f"{self.base_url}/api/enhanced/pipeline/trigger", json=payload
        )
        response.raise_for_status()
        return response.json()

    async def get_maintenance_status(self) -> dict[str, Any]:
        """Fetch the current graph-maintenance status.

        Returns:
            Dictionary with ``status`` and per-operation details under
            ``operations``.
        """
        response = await self._http_client.get(
            f"{self.base_url}/api/enhanced/maintenance/status"
        )
        response.raise_for_status()
        return response.json()

    async def trigger_maintenance(self, operation: str | None = None) -> dict[str, Any]:
        """Trigger a maintenance operation (e.g. ``prune``, ``reindex``).

        Args:
            operation: Optional maintenance operation name.

        Returns:
            Dictionary containing ``status`` and operation metadata.
        """
        payload: dict[str, Any] = {}
        if operation:
            payload["operation"] = operation
        response = await self._http_client.post(
            f"{self.base_url}/api/enhanced/maintenance/trigger", json=payload
        )
        response.raise_for_status()
        return response.json()

    async def list_kbs(self) -> list[dict[str, Any]]:
        """List all knowledge bases.

        Returns:
            List of KB summary dictionaries.
        """
        response = await self._http_client.get(f"{self.base_url}/api/enhanced/kb/list")
        response.raise_for_status()
        return response.json()

    async def search_kb(
        self, query: str, kb_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Hybrid search across one or all knowledge bases.

        Args:
            query: Free-text search query.
            kb_id: Optional KB identifier to scope the search.

        Returns:
            List of KB-hit dictionaries.
        """
        params: dict[str, str] = {"query": query}
        if kb_id:
            params["kb_id"] = kb_id
        response = await self._http_client.get(
            f"{self.base_url}/api/enhanced/kb/search", params=params
        )
        response.raise_for_status()
        return response.json()

    async def get_kb_article(self, article_id: str) -> dict[str, Any]:
        """Retrieve a KB article by id.

        Args:
            article_id: Unique article identifier.

        Returns:
            Article dictionary with full markdown content.
        """
        response = await self._http_client.get(
            f"{self.base_url}/api/enhanced/kb/article/{article_id}"
        )
        response.raise_for_status()
        return response.json()

    async def ingest_kb(self, source: str, kb_name: str) -> dict[str, Any]:
        """Ingest a source (file, directory, or URL) into a knowledge base.

        Args:
            source: Path or URL to ingest.
            kb_name: Name of the target knowledge base.

        Returns:
            Ingestion status dictionary.
        """
        response = await self._http_client.post(
            f"{self.base_url}/api/enhanced/kb/ingest",
            json={"source": source, "kb_name": kb_name},
        )
        response.raise_for_status()
        return response.json()

    async def create_memory(self, memory: dict[str, Any]) -> dict[str, Any]:
        """Create a new memory node in the knowledge graph.

        Args:
            memory: Memory payload sent to the backend.

        Returns:
            The created memory dictionary as returned by the server.
        """
        response = await self._http_client.post(
            f"{self.base_url}/api/enhanced/graph/memory", json=memory
        )
        response.raise_for_status()
        return response.json()

    async def get_memory(self, memory_id: str) -> dict[str, Any]:
        """Fetch a memory node by id.

        Args:
            memory_id: Memory identifier.

        Returns:
            Memory dictionary.
        """
        response = await self._http_client.get(
            f"{self.base_url}/api/enhanced/graph/memory/{memory_id}"
        )
        response.raise_for_status()
        return response.json()

    async def update_memory(
        self, memory_id: str, memory: dict[str, Any]
    ) -> dict[str, Any]:
        """Update an existing memory node.

        Args:
            memory_id: Memory identifier.
            memory: New memory payload.

        Returns:
            The updated memory dictionary.
        """
        response = await self._http_client.put(
            f"{self.base_url}/api/enhanced/graph/memory/{memory_id}", json=memory
        )
        response.raise_for_status()
        return response.json()

    async def delete_memory(self, memory_id: str) -> None:
        """Delete a memory node from the knowledge graph.

        Args:
            memory_id: Memory identifier.
        """
        response = await self._http_client.delete(
            f"{self.base_url}/api/enhanced/graph/memory/{memory_id}"
        )
        response.raise_for_status()

    async def list_specs(self) -> list[dict[str, Any]]:
        """List SDD specifications.

        Returns:
            List of specification dictionaries.
        """
        response = await self._http_client.get(
            f"{self.base_url}/api/enhanced/sdd/specs"
        )
        response.raise_for_status()
        return response.json()

    async def get_constitution(self) -> dict[str, Any]:
        """Fetch the current project constitution.

        Returns:
            Constitution dictionary (may be empty if not yet defined).
        """
        response = await self._http_client.get(
            f"{self.base_url}/api/enhanced/sdd/constitution"
        )
        response.raise_for_status()
        return response.json()

    async def list_plans(self) -> list[dict[str, Any]]:
        """List SDD implementation plans.

        Returns:
            List of plan dictionaries.
        """
        response = await self._http_client.get(
            f"{self.base_url}/api/enhanced/sdd/plans"
        )
        response.raise_for_status()
        return response.json()

    async def get_tasks(self, plan_id: str | None = None) -> list[dict[str, Any]]:
        """List SDD tasks, optionally scoped to a single plan.

        Args:
            plan_id: Optional plan identifier to filter on.

        Returns:
            List of task dictionaries.
        """
        params: dict[str, str] = {}
        if plan_id:
            params["plan_id"] = plan_id
        response = await self._http_client.get(
            f"{self.base_url}/api/enhanced/sdd/tasks", params=params
        )
        response.raise_for_status()
        return response.json()

    async def get_cron_calendar(self) -> list[dict[str, Any]]:
        """Fetch the scheduled cron task calendar.

        Returns:
            List of cron task dictionaries describing the schedule, last/next
            run timestamps, and current status.
        """
        response = await self._http_client.get(
            f"{self.base_url}/api/enhanced/cron/calendar"
        )
        response.raise_for_status()
        return response.json()

    async def get_cron_logs(self) -> list[dict[str, Any]]:
        """Fetch recent cron execution logs.

        Returns:
            List of cron log dictionaries (most recent first) containing the
            task name, start time, status, and output preview.
        """
        response = await self._http_client.get(
            f"{self.base_url}/api/enhanced/cron/logs"
        )
        response.raise_for_status()
        return response.json()

    async def get_backend_config(self) -> dict[str, Any]:
        """Retrieve the current backend configuration.

        Returns:
            Dictionary describing the backend type, connection settings, and
            environment overrides reported by the server.
        """
        response = await self._http_client.get(
            f"{self.base_url}/api/enhanced/config/backend"
        )
        response.raise_for_status()
        return response.json()

    async def update_backend_config(self, config: dict[str, Any]) -> dict[str, Any]:
        """Update the backend configuration.

        Args:
            config: Partial or full backend configuration dictionary.

        Returns:
            The server acknowledgement payload (usually contains a status and
            restart-required message).
        """
        response = await self._http_client.put(
            f"{self.base_url}/api/enhanced/config/backend", json=config
        )
        response.raise_for_status()
        return response.json()

    # ─────────────────────────────────────────────────────────────────
    #  Prompt Management (CONCEPT:TU-KG.compute.prompt-management-ahe-rollback)
    # ─────────────────────────────────────────────────────────────────

    async def list_prompts(self) -> list[dict[str, Any]]:
        """List all prompts from the KG.

        CONCEPT:TU-KG.compute.prompt-management-ahe-rollback — Prompt Management
        """
        response = await self._http_client.get(f"{self.base_url}/api/enhanced/prompts")
        response.raise_for_status()
        return response.json()

    async def get_prompt(self, prompt_id: str) -> dict[str, Any]:
        """Get a single prompt by ID.

        CONCEPT:TU-KG.compute.prompt-management-ahe-rollback — Prompt Management
        """
        response = await self._http_client.get(
            f"{self.base_url}/api/enhanced/prompts/{prompt_id}"
        )
        response.raise_for_status()
        return response.json()

    async def create_prompt(
        self, name: str, content: str, description: str = ""
    ) -> dict[str, Any]:
        """Create a new prompt in the KG.

        CONCEPT:TU-KG.compute.prompt-management-ahe-rollback — Prompt Management
        """
        response = await self._http_client.post(
            f"{self.base_url}/api/enhanced/prompts",
            json={"name": name, "content": content, "description": description},
        )
        response.raise_for_status()
        return response.json()

    async def update_prompt(self, prompt_id: str, content: str) -> dict[str, Any]:
        """Update a prompt (creates new version via SUPERSEDES).

        CONCEPT:TU-KG.compute.prompt-management-ahe-rollback — Prompt Management
        """
        response = await self._http_client.put(
            f"{self.base_url}/api/enhanced/prompts/{prompt_id}",
            json={"content": content},
        )
        response.raise_for_status()
        return response.json()

    async def get_prompt_versions(self, prompt_id: str) -> list[dict[str, Any]]:
        """Get version history for a prompt.

        CONCEPT:TU-KG.compute.prompt-management-ahe-rollback — Prompt Management
        """
        response = await self._http_client.get(
            f"{self.base_url}/api/enhanced/prompts/{prompt_id}/versions"
        )
        response.raise_for_status()
        return response.json()

    async def rollback_prompt(self, prompt_id: str, version_id: str) -> dict[str, Any]:
        """Rollback a prompt to a previous version.

        CONCEPT:TU-KG.compute.prompt-management-ahe-rollback
        Prompt Management (AHE Rollback).
        """
        response = await self._http_client.post(
            f"{self.base_url}/api/enhanced/prompts/{prompt_id}/rollback/{version_id}"
        )
        response.raise_for_status()
        return response.json()

    # ─────────────────────────────────────────────────────────────────
    #  Granular Resource Queries (CONCEPT:TU-KG.compute.granular-resource-queries)
    # ─────────────────────────────────────────────────────────────────

    async def list_skills_only(self) -> list[dict[str, Any]]:
        """List skills only (no MCP tools).

        CONCEPT:TU-KG.compute.granular-resource-queries — Granular Resource Queries
        """
        response = await self._http_client.get(f"{self.base_url}/api/enhanced/skills")
        response.raise_for_status()
        return response.json()

    async def list_tools_only(self) -> list[dict[str, Any]]:
        """List MCP tools only (no skills).

        CONCEPT:TU-KG.compute.granular-resource-queries — Granular Resource Queries
        """
        return await self.list_mcp_tools()

    async def toggle_resource(self, resource_id: str) -> dict[str, Any]:
        """Toggle enabled/disabled on any skill or tool.

        CONCEPT:TU-KG.compute.granular-resource-queries — Granular Resource Queries
        """
        # Try skills first, then tools
        for resource_type in ("skills", "tools"):
            try:
                response = await self._http_client.post(
                    f"{self.base_url}/api/enhanced/{resource_type}/{resource_id}/toggle"
                )
                if response.status_code == 200:
                    return response.json()
            except Exception:
                continue  # nosec B112
        raise ValueError(f"Resource {resource_id} not found")

    async def close(self) -> None:
        """Close the client."""
        await self._http_client.aclose()


def client_from_environment() -> AgentClient:
    """The client for ``AGENT_URL`` authenticated by ``AGENT_BEARER_TOKEN``."""
    return AgentClient(
        base_url=os.getenv("AGENT_URL", "http://localhost:8000"),
        bearer_token=os.getenv("AGENT_BEARER_TOKEN") or None,
    )
