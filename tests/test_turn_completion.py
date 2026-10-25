"""Normalized content cannot complete a mounted or headless turn."""

import io
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
from textual.widgets import Markdown, Static

from agent_terminal_ui.app import AgentApp, AgentEventReceived
from agent_terminal_ui.client import normalize_a2a_event
from agent_terminal_ui.headless import HeadlessRunner, StreamSink
from agent_terminal_ui.widgets.agent_response import AgentResponse

pytestmark = pytest.mark.spec("TUI-RUNTIME-R012.1.1")


def _text_events(chunks: list[str], event_type: str) -> list[dict[str, Any]]:
    events = []
    for chunk in chunks:
        events.extend(
            normalize_a2a_event(
                {
                    "kind": "artifact-update",
                    "taskId": "task-1",
                    "artifact": {"parts": [{"kind": "text", "text": chunk}]},
                },
                "context-1",
            )
        )
    for event in events:
        event["type"] = event_type
    return events


def _status_events(state: str, *, final: bool = True) -> list[dict[str, Any]]:
    return normalize_a2a_event(
        {
            "kind": "status-update",
            "taskId": "task-1",
            "status": {"state": state},
            "final": final,
        },
        "context-1",
    )


@pytest.mark.parametrize("event_type", ["text", "text_delta"])
@pytest.mark.parametrize(
    "chunks", [["[DONE]"], ["Literal [DONE] text"], ["[DO", "NE]"]]
)
async def test_mounted_literal_content_waits_for_terminal_before_queue(
    app: AgentApp, monkeypatch: pytest.MonkeyPatch, event_type: str, chunks: list[str]
) -> None:
    dispatch = Mock()
    monkeypatch.setattr(app, "_run_agent_turn", dispatch)
    async with app.run_test() as pilot:
        screen = app._get_main_screen()
        assert screen is not None
        screen.start_processing()
        app._is_processing = True
        queued = {"message": "next prompt", "parts": [], "timestamp": 0.0}
        app._user_message_queue = [queued]
        chunks = [*chunks, " and later text"]
        for event in _text_events(chunks, event_type) + _status_events(
            "completed", final=False
        ):
            await app.on_agent_event_received(AgentEventReceived(event))
            assert app._is_processing
            assert app._user_message_queue == [queued]
            dispatch.assert_not_called()
            assert "processing" in str(
                app.query_one("#status-thinking", Static).render()
            )
        await pilot.pause()
        assert "".join(
            response.content for response in app.query(AgentResponse)
        ) == "".join(chunks)
        assert "".join(
            response.query_one(Markdown)._markdown
            for response in app.query(AgentResponse)
        ) == "".join(chunks)

        for event in _status_events("completed"):
            await app.on_agent_event_received(AgentEventReceived(event))
        await pilot.pause()
        dispatch.assert_called_once_with(
            "next prompt", parts=[], model=app._current_model
        )
        assert app._user_message_queue == []
        assert app._is_processing

        for event in _status_events("canceled"):
            await app.on_agent_event_received(AgentEventReceived(event))
        assert not app._is_processing
        assert str(app.query_one("#status-thinking", Static).render()) == ""
        dispatch.assert_called_once()


async def test_mounted_terminal_approval_precedes_queued_turn(
    app: AgentApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    approval, dispatch = Mock(), Mock()
    monkeypatch.setattr(app, "_show_tool_approval_modal", approval)
    monkeypatch.setattr(app, "_run_agent_turn", dispatch)
    async with app.run_test():
        app._is_processing = True
        app._pending_tool_calls = {"call-1": {"needs_approval": True}}
        queued = {"message": "next prompt", "parts": [], "timestamp": 0.0}
        app._user_message_queue = [queued]
        for event in _text_events(["[DONE]"], "text"):
            await app.on_agent_event_received(AgentEventReceived(event))
        approval.assert_not_called()
        assert app._is_processing
        for event in _status_events("completed"):
            await app.on_agent_event_received(AgentEventReceived(event))
        approval.assert_called_once()
        dispatch.assert_not_called()
        assert app._user_message_queue == [queued]
        assert not app._is_processing


@pytest.mark.parametrize("event_type", ["text", "text_delta"])
@pytest.mark.parametrize(
    "chunks", [["[DONE]"], ["Literal [DONE] text"], ["[DO", "NE]"]]
)
@pytest.mark.parametrize("state", ["completed", "canceled", "failed", "rejected"])
async def test_headless_preserves_literal_content_and_typed_terminal_outcome(
    fake_client: AsyncMock, event_type: str, chunks: list[str], state: str
) -> None:
    events = (
        _text_events(chunks, event_type)
        + _status_events("completed", final=False)
        + _text_events([" and later text"], event_type)
        + _status_events(state)
        + _text_events(["not after terminal"], event_type)
    )
    consumed = []

    async def stream(*_args: Any, **_kwargs: Any):
        for event in events:
            consumed.append(event)
            yield event

    fake_client.stream = stream
    output = io.StringIO()
    runner = HeadlessRunner(fake_client, StreamSink(output))
    await runner.run_prompt("explain the literal marker")
    failed = state in {"failed", "rejected"}
    expected = "".join(chunks) + " and later text\n"
    if failed:
        expected += f"error: task {state}\n"
    assert output.getvalue() == expected
    assert runner.failed is failed
    assert consumed[-1]["type"] == "turn_end"
    assert consumed[-1]["state"] == state
