#!/usr/bin/python
# coding: utf-8
"""Workflow sidebar widget for the terminal UI.

Provides a visual representation of the agent's current graph execution state,
highlighting the active domain expert (e.g., Planner, Researcher) as the
agent moves through the multi-stage orchestration graph.
"""

from typing import Any
from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Label


class WorkflowSidebar(Vertical):
    """Sidebar widget to visualize the current agent execution state and graph nodes.

    Displays a list of available specialized agents and uses visual styling
    to indicate which node is currently active in the root graph.
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
        margin: 0 0 1 0;
        padding: 0 1;
    }

    .node-active {
        background: $primary;
        color: white;
        text-style: bold;
    }

    .node-pending {
        color: $text-muted;
    }
    """

    def __init__(self, **kwargs: Any) -> None:
        """Initialize the workflow sidebar.

        Args:
            **kwargs: Arguments passed to the base Vertical container.

        """
        super().__init__(**kwargs)
        self.active_node: str = "Basic"
        self.nodes: list[str] = [
            "Planner",
            "Researcher",
            "Programmer",
            "Architect",
            "QA",
        ]

    def compose(self) -> ComposeResult:
        """Construct the sidebar layout.

        Returns:
            A Textual ComposeResult containing the workflow title and node list.

        """
        yield Label("[bold]Workflow Execution[/bold]")
        with VerticalScroll(id="node-list"):
            for node in self.nodes:
                yield Label(
                    node, id=f"node-{node.lower()}", classes="node-item node-pending"
                )

    def update_state(self, node: str, status: str = "active") -> None:
        """Update the visual state of the sidebar to reflect the active node.

        Args:
            node: The identifier of the node that is now active.
            status: The status to apply (default is 'active').

        """
        self.active_node = node
        for n in self.nodes:
            try:
                widget = self.query_one(f"#node-{n.lower()}", Label)
                if n.lower() == node.lower():
                    widget.add_class("node-active")
                    widget.remove_class("node-pending")
                    widget.update(f"▶ {n}")
                else:
                    widget.remove_class("node-active")
                    widget.add_class("node-pending")
                    widget.update(n)
            except Exception:
                # Handle cases where the specific node label might not exist yet
                pass
