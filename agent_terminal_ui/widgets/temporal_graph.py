#!/usr/bin/python
"""Temporal Graph Widget.

A thin entrypoint that adds a bi-temporal time scrubber over the existing
:class:`GraphTree` text tree. The user types (or scrubs) a timestamp; on submit
the widget re-issues the base graph query with the engine's ``|> AS OF @<ts>``
operator (KG-2.250) appended and re-renders the tree at that historical instant.
Edges whose ``valid_until <= ts`` (expired) are rendered dimmed and tagged
``(expired)`` — the TUI honest equivalent of the webui greyed/dashed edges.

This widget contains no business logic: it adapts the timestamp input into a
query suffix (via :func:`with_as_of`) and renders whatever rows the backend
returns. Building the AS OF query string and classifying expired edges are pure
functions so they are unit-testable without a backend.

Concept: TUI-22 (Temporal Graph Scrubber)
"""

from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import Input, Label
from textual.widgets.tree import TreeNode

from agent_terminal_ui.widgets.graph_tree import GraphTree

# Base query re-issued at each scrubber instant. The backend translates UQL; we
# only append the temporal operator.
BASE_UQL = "MATCH (n) RETURN n LIMIT 200"


def with_as_of(query: str, iso_ts: str) -> str:
    """Append the bi-temporal ``|> AS OF @<ts>`` operator to a UQL query.

    Args:
        query: The base UQL query string.
        iso_ts: An ISO-8601 timestamp (e.g. ``2026-06-01T00:00:00Z``).

    Returns:
        The query with the temporal operator appended.
    """
    return f"{query.strip()} |> AS OF @{iso_ts}"


def is_edge_expired(edge: dict[str, Any], iso_ts: str) -> bool:
    """Return True when an edge has expired at ``iso_ts``.

    An edge is expired when it carries a ``valid_until`` that is non-null and
    lexicographically ``<= iso_ts`` (ISO-8601 strings sort chronologically).

    Args:
        edge: An edge/relationship dict, optionally carrying ``valid_until``.
        iso_ts: The current scrubber timestamp (ISO-8601).

    Returns:
        True when the edge is no longer live at ``iso_ts``.
    """
    valid_until = edge.get("valid_until")
    if not isinstance(valid_until, str) or not valid_until:
        return False
    return valid_until <= iso_ts


class TemporalGraph(Vertical):
    """A time-scrubbing graph view built on :class:`GraphTree`."""

    DEFAULT_CSS = """
    TemporalGraph {
        height: 100%;
    }
    TemporalGraph #temporal-ts-input {
        margin: 0 1;
    }
    TemporalGraph #temporal-hint {
        color: $text-muted;
        margin: 0 1;
    }
    """

    class AsOfRequested(Message):
        """Emitted when the user submits a new AS OF timestamp."""

        def __init__(self, iso_ts: str, query: str) -> None:
            super().__init__()
            self.iso_ts = iso_ts
            self.query = query

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._current_ts: str = ""

    def compose(self) -> ComposeResult:
        yield Label("AS OF timestamp (ISO-8601):", id="temporal-hint")
        yield Input(
            placeholder="2026-06-01T00:00:00Z — empty = now",
            id="temporal-ts-input",
        )
        yield GraphTree("Graph @ now", id="temporal-graph-tree")

    @property
    def tree(self) -> GraphTree:
        """The underlying text tree."""
        return self.query_one("#temporal-graph-tree", GraphTree)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Scrub: rebuild the query for the entered timestamp and announce it."""
        iso_ts = event.value.strip()
        self._current_ts = iso_ts
        query = with_as_of(BASE_UQL, iso_ts) if iso_ts else BASE_UQL
        self.tree.root.set_label(f"Graph @ {iso_ts or 'now'}")
        self.post_message(self.AsOfRequested(iso_ts, query))

    def render_as_of(
        self,
        nodes: list[dict[str, Any]],
        edges: list[dict[str, Any]],
        iso_ts: str,
    ) -> None:
        """Render nodes/edges at ``iso_ts``, dimming expired edges.

        Args:
            nodes: Node dicts (each with at least an ``id``/``name``).
            edges: Relationship dicts (``source``/``target``/``type`` and
                optionally ``valid_until``).
            iso_ts: The current scrubber timestamp; empty means "now".
        """
        tree = self.tree
        tree.root.remove_children()
        tree.root.set_label(f"Graph @ {iso_ts or 'now'}")

        # Build a node-id -> TreeNode map as we add nodes, so edges can be nested
        # under their source without stashing attributes on the TreeNode.
        children_by_id: dict[str, TreeNode[dict[str, Any]]] = {}
        for node in nodes:
            node_id = str(node.get("id") or node.get("name") or "?")
            label = str(node.get("name") or node.get("id") or "node")
            child = tree.root.add(f"[bold]{label}[/]", data=node, expand=False)
            children_by_id[node_id] = child

        # Attach edges under their source node, dimming the expired ones.
        for edge in edges:
            source = str(edge.get("source", "?"))
            target = str(edge.get("target", "?"))
            rel = str(edge.get("type", "rel"))
            parent = children_by_id.get(source, tree.root)
            if is_edge_expired(edge, iso_ts):
                parent.add_leaf(f"[dim]{rel} → {target} (expired)[/]", data=edge)
            else:
                parent.add_leaf(f"{rel} → [primary]{target}[/]", data=edge)
        tree.root.expand()
