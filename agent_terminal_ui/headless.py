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

import os
import sys
from typing import Any, Protocol, TextIO, runtime_checkable

from agent_terminal_ui.client import AgentClient

# Events that end a turn (mirrors screens/main.py handling).
_DONE_MARKER = "[DONE]"


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
            if _DONE_MARKER in content:
                self._sink.turn_end()
                return True
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
) -> None:
    """Run a single headless agent turn for ``prompt`` against the backend.

    Builds an :class:`AgentClient` bound to ``AGENT_URL`` (default
    ``http://localhost:8000``), streams the turn to stdout, and closes the
    client. No Textual application is created.
    """
    client = AgentClient(base_url=os.getenv("AGENT_URL", "http://localhost:8000"))
    try:
        await HeadlessRunner(client).run_prompt(prompt, mode_id=mode_id, model=model)
    finally:
        await client.aclose()
