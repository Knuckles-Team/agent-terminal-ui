"""Bounded consumer of Arbora's public, flat execution graph projection."""

from __future__ import annotations

import json
from dataclasses import dataclass
from graphlib import TopologicalSorter
from typing import TypeGuard

from agent_terminal_ui.public_run_events import MAX_PAGE_BYTES

GRAPH_SCHEMA = "arbora-execution-graph-v1"
MAX_NODES = 64
MAX_EDGES = 2016
MAX_COVERED_EVENTS = 1000
STATUSES = frozenset(
    {"unobserved", "running", "completed", "failed", "cancelled", "blocked"}
)


def graph_identifier(value: object, maximum: int = 512) -> TypeGuard[str]:
    """Keep opaque producer identities intact; filter controls only when displayed."""
    return isinstance(value, str) and bool(value.strip()) and len(value) <= maximum


@dataclass(frozen=True)
class ExecutionStep:
    key: str
    task_id: str
    status: str
    event_id: str | None
    sequence: int | None

    @classmethod
    def parse(cls, value: object, run_id: str, covered_after: int) -> ExecutionStep:
        if not isinstance(value, dict):
            raise ValueError("invalid execution step")
        task_id, status = value.get("task_id"), value.get("status")
        if (
            not graph_identifier(task_id)
            or value.get("kind") != "plan_step"
            or not isinstance(status, str)
            or status not in STATUSES
            or value.get("key")
            != json.dumps([run_id, "plan_step", task_id], separators=(",", ":"))
        ):
            raise ValueError("invalid execution step binding")
        event_id, sequence = None, None
        evidence = value.get("evidence")
        if status == "unobserved":
            if evidence is not None:
                raise ValueError("unobserved step has evidence")
        else:
            if not isinstance(evidence, dict):
                raise ValueError("observed step lacks evidence")
            event_id, sequence = evidence.get("event_id"), evidence.get("sequence")
            if (
                not graph_identifier(event_id, 1024)
                or type(sequence) is not int
                or not 0 < sequence <= covered_after
            ):
                raise ValueError("invalid step evidence")
        return cls(value["key"], task_id, status, event_id, sequence)


@dataclass(frozen=True)
class ExecutionGraph:
    run_id: str
    task_id: str
    plan_digest: str
    nodes: tuple[ExecutionStep, ...]
    edges: tuple[tuple[str, str], ...]
    covered_after: int
    has_more: bool

    @classmethod
    def parse(
        cls, value: object, run_id: str, task_id: str | None = None
    ) -> ExecutionGraph:
        if (
            not graph_identifier(run_id)
            or (task_id is not None and not graph_identifier(task_id))
            or not isinstance(value, dict)
            or value.get("schema_version") != GRAPH_SCHEMA
            or value.get("availability") != "available"
            or value.get("run_id") != run_id
            or not graph_identifier(value.get("task_id"))
            or (task_id is not None and value["task_id"] != task_id)
            or len(json.dumps(value).encode()) > MAX_PAGE_BYTES
        ):
            raise ValueError("execution graph unavailable")
        snapshot = value.get("snapshot")
        if not isinstance(snapshot, dict):
            raise ValueError("execution snapshot unavailable")
        covered = snapshot.get("covered_after")
        if (
            not graph_identifier(snapshot.get("plan_digest"))
            or snapshot.get("topology_completeness") != "complete"
            or snapshot.get("lifecycle_completeness") != "incomplete"
            or snapshot.get("lifecycle_reason") != "observed_prefix_only"
            or type(covered) is not int
            or not 0 <= covered <= MAX_COVERED_EVENTS
            or type(snapshot.get("has_more")) is not bool
            or any(
                snapshot.get(capability) is not False
                for capability in (
                    "can_read_transcript",
                    "can_message_active",
                    "can_continue_completed",
                    "supports_spawned_children",
                )
            )
        ):
            raise ValueError("unsupported execution snapshot")
        raw_nodes, raw_edges = snapshot.get("nodes"), snapshot.get("edges")
        if (
            not isinstance(raw_nodes, list)
            or not 0 < len(raw_nodes) <= MAX_NODES
            or not isinstance(raw_edges, list)
            or len(raw_edges) > MAX_EDGES
        ):
            raise ValueError("execution graph exceeds bounds")
        nodes = tuple(ExecutionStep.parse(node, run_id, covered) for node in raw_nodes)
        observed = [node for node in nodes if node.event_id is not None]
        if len({node.event_id for node in observed}) != len(observed) or len(
            {node.sequence for node in observed}
        ) != len(observed):
            raise ValueError("duplicate lifecycle evidence")
        dependencies: dict[str, set[str]] = {node.key: set() for node in nodes}
        if len(dependencies) != len(nodes):
            raise ValueError("duplicate execution step")
        edges = []
        for edge in raw_edges:
            if not isinstance(edge, dict) or edge.get("kind") != "depends_on":
                raise ValueError("unsupported execution edge")
            source, target = edge.get("source"), edge.get("target")
            if (
                not isinstance(source, str)
                or not isinstance(target, str)
                or source not in dependencies
                or target not in dependencies
                or source in dependencies[target]
            ):
                raise ValueError("invalid dependency endpoint")
            dependencies[target].add(source)
            edges.append((source, target))
        tuple(TopologicalSorter(dependencies).static_order())
        return cls(
            run_id,
            value["task_id"],
            snapshot["plan_digest"],
            nodes,
            tuple(edges),
            covered,
            snapshot["has_more"],
        )
