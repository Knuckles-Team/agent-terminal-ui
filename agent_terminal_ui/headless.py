"""Headless run mode for agent-terminal-ui.

A thin driver that runs the agent loop over :class:`AgentClient` and renders
events to a plain text stream, with no Textual application or widget tree. This
is the lightweight substrate for running many concurrent, non-interactive agent
sessions (e.g. ``--prompt`` automation) against one shared backend: importing
this module pulls in only the HTTP client and stdlib, not the TUI.

Rendering goes through a :class:`RenderSink` so the interactive ``Conversation``
widget and this headless ``StreamSink`` present the same event vocabulary.
"""

from __future__ import annotations

import asyncio
import sys
from typing import Any, Protocol, TextIO, runtime_checkable

import httpx

from agent_terminal_ui.client import (
    A2ATransportError,
    AgentClient,
    client_from_environment,
)


@runtime_checkable
class RenderSink(Protocol):
    """The minimal surface used to render agent events.

    The interactive ``Conversation`` widget satisfies a richer version of this;
    headless mode binds the plain-text :class:`StreamSink`.
    """

    def agent_text(self, text: str) -> None:
        """Render a (possibly partial) chunk of agent response text."""

    def tool_call(self, name: str, call_id: str, summary: str) -> None:
        """Render the start of a tool call."""

    def tool_output(self, call_id: str, status: str, summary: str) -> None:
        """Render the result of a tool call."""

    def info(self, text: str) -> None:
        """Render an informational line."""

    def error(self, text: str) -> None:
        """Render an error line."""

    def turn_end(self) -> None:
        """Signal that the agent turn has finished."""


class StreamSink:
    """A :class:`RenderSink` that writes plain text to an output stream."""

    def __init__(self, stream: TextIO | None = None) -> None:
        self._out = stream if stream is not None else sys.stdout
        self._mid_response = False

    def _write(self, text: str) -> None:
        self._out.write(text)
        self._out.flush()

    def agent_text(self, text: str) -> None:
        if not text:
            return
        self._mid_response = True
        self._write(text)

    def _end_response(self) -> None:
        if self._mid_response:
            self._write("\n")
            self._mid_response = False

    def tool_call(self, name: str, call_id: str, summary: str) -> None:
        self._end_response()
        suffix = f" {summary}" if summary else ""
        self._write(f"→ {name}{suffix}\n")

    def tool_output(self, call_id: str, status: str, summary: str) -> None:
        marker = "✓" if status == "completed" else "✗"
        suffix = f" {summary}" if summary else ""
        self._write(f"  {marker} {status}{suffix}\n")

    def info(self, text: str) -> None:
        self._end_response()
        self._write(f"{text}\n")

    def error(self, text: str) -> None:
        self._end_response()
        self._write(f"error: {text}\n")

    def turn_end(self) -> None:
        self._end_response()


class HeadlessRunner:
    """Runs agent turns over the wire and renders them through a sink."""

    def __init__(self, client: AgentClient, sink: RenderSink | None = None) -> None:
        self._client = client
        self._sink = sink if sink is not None else StreamSink()
        self.failed = False

    async def run_prompt(
        self,
        prompt: str,
        *,
        session_id: str | None = None,
        mode_id: str = "ask",
        model: str | None = None,
    ) -> None:
        """Stream one agent turn for ``prompt`` and render it, then return."""
        async for event in self._client.stream(
            prompt,
            session_id=session_id,
            parts=None,
            mode_id=mode_id,
            model=model,
        ):
            if self._dispatch(event):
                break

    def _dispatch(self, event: dict[str, Any]) -> bool:
        """Render one event. Returns True when the turn has ended."""
        event_type = event.get("type")

        if event_type in ("text", "text_delta"):
            content = event.get("content", "")
            self._sink.agent_text(content)
        elif event_type == "tool_call":
            data = event.get("data", {})
            self._sink.tool_call(
                data.get("name", "tool"),
                data.get("call_id", ""),
                _summarize(data.get("input") or data.get("args")),
            )
        elif event_type == "tool_output":
            data = event.get("data", {})
            status = "failed" if data.get("error") else "completed"
            self._sink.tool_output(
                data.get("call_id", ""),
                status,
                str(data.get("error") or _summarize(data.get("output"))),
            )
        elif event_type == "error":
            self.failed = True
            self._sink.error(event.get("message", "unknown error"))
        elif event_type == "turn_end":
            self._sink.turn_end()
            return True
        return False


def _summarize(value: Any, limit: int = 120) -> str:
    """Render a tool input/output value as a short single-line string."""
    if value is None:
        return ""
    text = " ".join(str(value).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


async def run_headless(
    prompt: str,
    *,
    mode_id: str = "ask",
    model: str | None = None,
    session_id: str | None = None,
) -> bool:
    """Run a single headless agent turn for ``prompt`` against the backend.

    Builds the :class:`AgentClient` for ``AGENT_URL`` and ``AGENT_BEARER_TOKEN``,
    streams the turn to stdout, prints the session to resume on stderr, and
    closes the client. No Textual application is created.

    Returns:
        False when the turn reported an error.
    """
    client = client_from_environment()
    runner = HeadlessRunner(client)
    try:
        await runner.run_prompt(
            prompt, session_id=session_id, mode_id=mode_id, model=model
        )
    finally:
        await client.aclose()
    if client.current_session_id:
        sys.stderr.write(f"session: {client.current_session_id}\n")
    return not runner.failed


_OBSERVED_STATES = frozenset(
    {
        "submitted",
        "queued",
        "working",
        "running",
        "input-required",
        "completed",
        "canceled",
        "failed",
        "rejected",
    }
)
_OBSERVED_END = frozenset(
    {"completed", "canceled", "failed", "rejected", "input-required"}
)


def _valid_task_id(value: object) -> bool:
    return (
        isinstance(value, str)
        and 0 < len(value) <= 512
        and value.isprintable()
        and bool(value.strip())
    )


def _task_identity(task: dict[str, Any], task_id: str) -> tuple[str, str | None, str]:
    context = task.get("contextId")
    status = task.get("status")
    state = status.get("state") if isinstance(status, dict) else None
    metadata = task.get("metadata", {})
    if not isinstance(metadata, dict):
        raise ValueError("invalid task metadata")
    owner = metadata.get("arbora", {})
    if not isinstance(owner, dict):
        raise ValueError("invalid task metadata")
    run = owner.get("runId")
    if task.get("id") != task_id or not _valid_task_id(context):
        raise ValueError("invalid task identity")
    if run is not None and not _valid_task_id(run):
        raise ValueError("invalid run identity")
    if not isinstance(state, str) or state not in _OBSERVED_STATES:
        raise ValueError("unknown task state")
    if not isinstance(context, str) or (run is not None and not isinstance(run, str)):
        raise ValueError("invalid task identity")
    return context, run, state


def _task_output(task: dict[str, Any]) -> str | None:
    artifacts = task.get("artifacts")
    if not artifacts:
        return None
    if not isinstance(artifacts, list):
        raise ValueError("invalid task output")
    texts: list[str] = []
    size = 0
    for artifact in artifacts:
        parts = artifact.get("parts") if isinstance(artifact, dict) else None
        if not isinstance(parts, list):
            raise ValueError("invalid task output")
        for part in parts:
            if not isinstance(part, dict) or part.get("kind") != "text":
                raise ValueError("unsupported task output")
            text = part.get("text")
            if not isinstance(text, str):
                raise ValueError("invalid task output")
            size += len(text)
            if size > 1_000_000:
                raise ValueError("task output exceeds display limit")
            texts.append(text)
    return "".join(texts) if texts else None


async def observe_task(client: AgentClient, task_id: str, sink: RenderSink) -> bool:
    """Read an existing task until it ends or needs input; never submit effects."""
    if not _valid_task_id(task_id):
        sink.error("Task unavailable: invalid task ID")
        return False
    context: str | None = None
    run: str | None = None
    previous: tuple[str, str | None, str] | None = None
    try:
        while True:
            task = await client.get_task(task_id)
            next_context, next_run, state = _task_identity(task, task_id)
            if context is not None and next_context != context:
                raise ValueError("task context changed")
            if run is not None and next_run is not None and next_run != run:
                raise ValueError("task run changed")
            context, run = next_context, next_run or run
            output = _task_output(task) if state == "completed" else None
            current = (context, run, state)
            if current != previous:
                sink.info(
                    f"task: {task_id} | context: {context} | "
                    f"run: {run or 'unavailable'}"
                )
                sink.info(f"state: {state}")
                previous = current
            if state in _OBSERVED_END:
                if state == "completed" and output is not None:
                    sink.agent_text(
                        "".join(c for c in output if c.isprintable() or c in "\n\t")
                    )
                    sink.turn_end()
                else:
                    sink.info("output: unavailable")
                if state == "input-required":
                    sink.info("Detached: approval or input remains required")
                sink.info("terminal reason: unavailable")
                return state in {"completed", "canceled", "input-required"}
            await asyncio.sleep(client.poll_interval)
    except (A2ATransportError, httpx.HTTPError, ValueError):
        sink.error(
            "Task unavailable: read refused or response invalid; observation stopped"
        )
        return False


async def run_task_observer(task_id: str) -> bool:
    """Build the existing authenticated client and close it after observation."""
    client = client_from_environment()
    try:
        return await observe_task(client, task_id, StreamSink())
    finally:
        await client.aclose()
