#!/usr/bin/python
"""Graph Tree Widget.

This module provides a Textual Tree widget for visualizing Pydantic agent graphs,
swarm hierarchies, and Knowledge Graph nodes in a hierarchical manner.
"""

from typing import Any

from rich.text import Text
from textual.message import Message
from textual.widgets import Tree
from textual.widgets.tree import TreeNode


class GraphTree(Tree[dict[str, Any]]):
    """A Textual Tree widget for displaying agent swarms and knowledge graphs."""

    class NodeClicked(Message):
        """Message emitted when a graph node with data is clicked."""

        def __init__(self, data: dict[str, Any]) -> None:
            super().__init__()
            self.data = data

    def __init__(self, name: str, **kwargs) -> None:
        super().__init__(name, **kwargs)
        self.root.expand()

    def add_agent_node(
        self,
        parent_node: TreeNode[dict[str, Any]],
        agent_id: str,
        role: str,
        status: str = "pending",
        data: dict[str, Any] | None = None,
    ) -> TreeNode[dict[str, Any]]:
        """Add an agent node to the tree with rich formatting.

        Args:
            parent_node: The parent node to attach to.
            agent_id: The ID of the agent.
            role: The role (e.g., orchestrator, specialist).
            status: The current status of the agent.
            data: Arbitrary data bound to the node (like chat messages).

        Returns:
            The newly created tree node.
        """
        if status == "active":
            label = Text.from_markup(
                f"→ [bold primary]{agent_id}[/] [[dim italic]{role}[/]] (active)"
            )
        elif status == "completed":
            label = Text.from_markup(
                f"✓ [bold success]{agent_id}[/] [[dim italic]{role}[/]] (completed)"
            )
        else:
            label = Text.from_markup(
                f"  [bold]{agent_id}[/] [[dim italic]{role}[/]] ({status})"
            )

        return parent_node.add(label, data=data, expand=True)

    def on_tree_node_selected(self, event: Tree.NodeSelected[dict[str, Any]]) -> None:
        """Handle node selection events."""
        node = event.node
        if node and node.data and "messages" in node.data:
            self.post_message(self.NodeClicked(node.data))

    def update_agent_status(self, node: TreeNode[dict[str, Any]], status: str) -> None:
        """Update the status of an existing agent node."""
        if not node or not node.data:
            return

        agent_id = node.data.get("agent_id", "Unknown")
        role = node.data.get("role", "agent")

        if status == "active":
            label = Text.from_markup(
                f"→ [bold primary]{agent_id}[/] [[dim italic]{role}[/]] (active)"
            )
        elif status == "completed":
            label = Text.from_markup(
                f"✓ [bold success]{agent_id}[/] [[dim italic]{role}[/]] (completed)"
            )
        else:
            label = Text.from_markup(
                f"  [bold]{agent_id}[/] [[dim italic]{role}[/]] ({status})"
            )

        node.set_label(label)
        self.refresh()
