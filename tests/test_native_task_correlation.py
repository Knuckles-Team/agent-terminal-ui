"""Shared public A2A fixtures for Python and the native correlation model."""

import json
from pathlib import Path

import pytest

from agent_terminal_ui.client import normalize_a2a_event


@pytest.mark.spec("TUI-RUNTIME-R002.1.1")
def test_shared_wire_fixture_uses_python_normalizer() -> None:
    fixture = Path(__file__).with_name("fixtures") / "a2a_task_correlation.json"
    with fixture.open() as stream:
        wire_events = json.load(stream)
    events = [
        event
        for wire_event in wire_events
        for event in normalize_a2a_event(wire_event, wire_event["contextId"])
    ]
    assert [event["type"] for event in events] == [
        "sideband",
        "sideband",
        "text",
        "sideband",
        "turn_end",
    ]
    assert all(event["task_id"] == "server-task-1" for event in events)
    assert all(event["session_id"] == "server-context-2" for event in events)
    assert events[-1]["run_id"] == "server-run-3"
    assert events[2]["content"] == "the answer"
    assert "run_id" not in events[2]
