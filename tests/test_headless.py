"""Tests for the headless thin runner and its stream sink."""

import io
from unittest.mock import AsyncMock

import pytest

from agent_terminal_ui.headless import HeadlessRunner, RenderSink, StreamSink


def _events():
    return [
        {"type": "text", "content": "Hello "},
        {"type": "text", "content": "world"},
        {
            "type": "tool_call",
            "data": {"name": "shell", "call_id": "c1", "input": "ls -la"},
        },
        {"type": "tool_output", "data": {"call_id": "c1", "output": "file_a\nfile_b"}},
        {"type": "tool_output", "data": {"call_id": "c2", "error": "boom"}},
        {"type": "error", "message": "transient failure"},
        {"type": "turn_end"},
        {"type": "text", "content": "should not be rendered"},
    ]


def _client_yielding(events):
    client = AsyncMock()

    async def _stream(*_args, **_kwargs):
        for event in events:
            yield event

    client.stream = _stream
    return client


def test_stream_sink_is_a_render_sink() -> None:
    assert isinstance(StreamSink(io.StringIO()), RenderSink)


async def test_runner_renders_events_to_stream() -> None:
    out = io.StringIO()
    runner = HeadlessRunner(_client_yielding(_events()), StreamSink(out))
    await runner.run_prompt("do the thing")
    text = out.getvalue()

    assert "Hello world" in text
    assert "→ shell ls -la" in text
    assert "✓ completed file_a file_b" in text
    assert "✗ failed boom" in text
    assert "error: transient failure" in text
    # turn_end stops the loop: the post-turn text is never rendered.
    assert "should not be rendered" not in text


async def test_runner_stops_on_done_marker() -> None:
    out = io.StringIO()
    events = [
        {"type": "text", "content": "partial"},
        {"type": "text", "content": "[DONE]"},
        {"type": "text", "content": "after done"},
    ]
    runner = HeadlessRunner(_client_yielding(events), StreamSink(out))
    await runner.run_prompt("x")
    assert "after done" not in out.getvalue()


async def test_run_prompt_passes_through_client_kwargs() -> None:
    client = AsyncMock()
    captured = {}

    async def _stream(prompt, **kwargs):
        captured["prompt"] = prompt
        captured.update(kwargs)
        for _ in ():
            yield _

    client.stream = _stream
    await HeadlessRunner(client, StreamSink(io.StringIO())).run_prompt(
        "hi", mode_id="plan", model="claude-opus-4-8"
    )
    assert captured["prompt"] == "hi"
    assert captured["mode_id"] == "plan"
    assert captured["model"] == "claude-opus-4-8"


@pytest.mark.parametrize(
    "value,expected",
    [(None, ""), ("a   b\n c", "a b c"), ("x" * 200, "x" * 119 + "…")],
)
def test_summarize(value, expected) -> None:
    from agent_terminal_ui.headless import _summarize

    assert _summarize(value) == expected
