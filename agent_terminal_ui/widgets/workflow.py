#!/usr/bin/python
# coding: utf-8
"""Workflow sidebar widget for the terminal UI.

Provides a dynamic visual representation of the agent's current graph
execution state.  Nodes are discovered at runtime from sideband events
rather than being hardcoded, so the sidebar automatically adapts to
the graph topology (including dynamic MCP agents).
"""

from typing import Any
from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Label

# Phase labels for semantic grouping of graph events
_PHASE_MAP: dict[str, str] = {
    "router": "Planning",
    "planner": "Planning",
    "memory_selection": "Planning",
    "researcher": "Discovery",
    "architect": "Discovery",
    "verifier": "Validation",
    "error_recovery": "Recovery",
    "dispatcher": "Orchestration",
}


class WorkflowSidebar(Vertical):
    """Sidebar widget to visualize the current agent execution state and graph nodes.

    Nodes are populated dynamically from sideband events.  The sidebar
    shows the current execution phase and highlights the active node.
    """

    DEFAULT_CSS: str = """
    WorkflowSidebar {
        width: 30;
        background: $surface;
        border-left: solid $primary;
        padding: 1;
    }

    #node-list {
        height: 1fr;
    }

    .node-item {
        margin: 0 0 0 0;
        padding: 0 1;
    }

    .node-active {
        background: $primary;
        color: white;
        text-style: bold;
    }

    .node-completed {
        color: $success;
    }

    .node-pending {
        color: $text-muted;
    }

    .phase-label {
        color: $accent;
        text-style: bold italic;
        margin: 1 0 0 0;
    }
    """

    def __init__(self, **kwargs: Any) -> None:
        """Initialize the workflow sidebar.

        Args:
            **kwargs: Arguments passed to the base Vertical container.

        """
        super().__init__(**kwargs)
        self.active_node: str = ""
        self.nodes: list[str] = []
        self.completed_nodes: set[str] = set()
        self.current_phase: str = ""

    def compose(self) -> ComposeResult:
        """Construct the sidebar layout.

        Returns:
            A Textual ComposeResult containing the workflow title, phase
            label, and scrollable node list.

        """
        yield Label("[bold]Workflow[/bold]")
        yield Label("", id="phase-label", classes="phase-label")
        yield VerticalScroll(id="node-list")

    def update_state(self, node: str, status: str = "active") -> None:
        """Update the visual state of the sidebar to reflect the active node.

        If the node has not been seen before, it is dynamically added to
        the sidebar.  The current phase label is updated based on the node
        type.

        Args:
            node: The identifier of the node that is now active.
            status: The status to apply ('active', 'completed', 'pending').

        """
        if not node:
            return

        # Mark previous active node as completed
        if self.active_node and self.active_node != node:
            self.completed_nodes.add(self.active_node)

        self.active_node = node

        # Dynamically add the node if it hasn't been seen before
        if node not in self.nodes:
            self.nodes.append(node)
            try:
                container = self.query_one("#node-list", VerticalScroll)
                display_name = node.replace("_", " ").title()
                label = Label(
                    display_name,
                    id=f"node-{node.lower()}",
                    classes="node-item node-pending",
                )
                container.mount(label)
            except Exception:
                pass

        # Update phase label
        phase = _PHASE_MAP.get(node.lower(), "Execution")
        if phase != self.current_phase:
            self.current_phase = phase
            try:
                self.query_one("#phase-label", Label).update(
                    f"[italic]{phase}[/italic]"
                )
            except Exception:
                pass

        # Update visual state of all nodes
        for n in self.nodes:
            try:
                widget = self.query_one(f"#node-{n.lower()}", Label)
                display_name = n.replace("_", " ").title()
                if n == node:
                    widget.remove_class("node-pending", "node-completed")
                    widget.add_class("node-active")
                    widget.update(f"▶ {display_name}")
                elif n in self.completed_nodes:
                    widget.remove_class("node-pending", "node-active")
                    widget.add_class("node-completed")
                    widget.update(f"✓ {display_name}")
                else:
                    widget.remove_class("node-active", "node-completed")
                    widget.add_class("node-pending")
                    widget.update(f"  {display_name}")
            except Exception:
                pass
