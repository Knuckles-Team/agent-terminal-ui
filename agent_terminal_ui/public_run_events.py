"""Bounded, read-only consumer of Arbora's explicit public event projection."""

from __future__ import annotations

import json
from dataclasses import dataclass

from agent_terminal_ui.display_text import display_text

SCHEMA = "arbora-run-events-v1"
MAX_EVENTS = 1000
MAX_VIEW_BYTES = 131_072
MAX_PAGE_BYTES = 1_048_576
MAX_SEQUENCE = 2**63 - 1
TRACE_TYPES = frozenset(
    {
        "run_started",
        "node_transition",
        "graph_complete",
        "error",
        "run_cancelled",
        "task_started",
        "task_completed",
        "task_failed",
        "task_cancelled",
        "task_blocked",
    }
)
TERMINAL_TYPES = frozenset({"graph_complete", "error", "run_cancelled"})


def identifier(value: object, maximum: int = 512) -> bool:
    """Whether a server identity is usable without coercion or control text."""
    return (
        isinstance(value, str)
        and bool(value.strip())
        and len(value) <= maximum
        and display_text(value, multiline=False) == value
    )


@dataclass(frozen=True)
class PublicRunEvent:
    event_id: str
    sequence: int
    run_id: str
    task_id: str
    kind: str
    summary: str | None
    text: str
    terminal: bool

    @classmethod
    def parse(cls, value: object, run_id: str) -> PublicRunEvent:
        if not isinstance(value, dict):
            raise ValueError("invalid public event")
        sequence, kind = value.get("sequence"), value.get("type")
        if (
            value.get("schema_version") != SCHEMA
            or value.get("run_id") != run_id
            or not identifier(value.get("event_id"), 1024)
            or not identifier(value.get("task_id"))
            or type(sequence) is not int
            or not 0 < sequence <= MAX_SEQUENCE
            or not isinstance(kind, str)
            or kind not in TRACE_TYPES | {"public_summary"}
            or type(value.get("terminal")) is not bool
            or value["terminal"] != (kind in TERMINAL_TYPES)
        ):
            raise ValueError("invalid public event binding")
        summary = None
        payload = value.get("payload")
        if not isinstance(payload, dict):
            raise ValueError("invalid public event payload")
        if kind == "public_summary":
            raw_summary = payload.get("summary")
            if (
                value.get("category") != "public_summary"
                or not isinstance(raw_summary, str)
                or not 0 < len(raw_summary) <= 16_384
            ):
                raise ValueError("invalid public summary")
            summary = display_text(raw_summary)
            text = summary
        else:
            if value.get("category") != "execution_trace":
                raise ValueError("invalid execution trace")
            fields = []
            for key in ("status", "node", "from_node", "to_node", "error_type"):
                if key in payload:
                    item = payload[key]
                    if not isinstance(item, str) or len(item) > 256:
                        raise ValueError("invalid trace field")
                    fields.append(f"{key}: {display_text(item)}")
            if "step" in payload:
                step = payload["step"]
                if type(step) is not int or not 0 <= step <= MAX_SEQUENCE:
                    raise ValueError("invalid trace step")
                fields.append(f"step: {step}")
            if "depends_on" in payload:
                dependencies = payload["depends_on"]
                if (
                    not isinstance(dependencies, list)
                    or len(dependencies) > 64
                    or not all(identifier(item) for item in dependencies)
                ):
                    raise ValueError("invalid trace dependencies")
                fields.append(f"depends_on: {', '.join(dependencies)}")
            text = f"{sequence}. {kind} · task {value['task_id']}"
            if fields:
                text += "\n" + "\n".join(fields)
        return cls(
            value["event_id"],
            sequence,
            run_id,
            value["task_id"],
            kind,
            summary,
            text,
            value["terminal"],
        )


@dataclass(frozen=True)
class PublicRunPage:
    events: tuple[PublicRunEvent, ...]
    next_after: int
    has_more: bool
    terminal: bool

    @classmethod
    def parse(cls, value: object, run_id: str, after: int) -> PublicRunPage:
        if (
            not identifier(run_id)
            or type(after) is not int
            or not 0 <= after <= MAX_SEQUENCE
            or not isinstance(value, dict)
            or value.get("schema_version") != SCHEMA
            or value.get("run_id") != run_id
            or value.get("availability") != "available"
            or type(value.get("after")) is not int
            or value["after"] != after
            or len(json.dumps(value).encode()) > MAX_PAGE_BYTES
        ):
            raise ValueError("public run details unavailable")
        raw = value.get("events")
        if not isinstance(raw, list) or len(raw) > MAX_EVENTS:
            raise ValueError("invalid public event window")
        events = tuple(PublicRunEvent.parse(item, run_id) for item in raw)
        ids: set[str] = set()
        for index, event in enumerate(events):
            if (
                event.sequence != after + index + 1
                or event.event_id in ids
                or (index and events[index - 1].terminal)
            ):
                raise ValueError("public event history gap or duplicate")
            ids.add(event.event_id)
        expected = events[-1].sequence if events else after
        if (
            type(value.get("next_after")) is not int
            or value["next_after"] != expected
            or type(value.get("has_more")) is not bool
            or type(value.get("terminal")) is not bool
            or value["terminal"]
            != bool(
                (events and events[-1].terminal)
                or (not events and after > 0 and value["terminal"])
            )
            or (value["has_more"] and (not events or value["terminal"]))
        ):
            raise ValueError("invalid public event cursor")
        return cls(events, expected, value["has_more"], value["terminal"])
