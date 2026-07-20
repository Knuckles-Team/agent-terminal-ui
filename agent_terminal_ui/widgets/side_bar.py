"""Unified sidebar widget.

Combines the Plan, Workflow, and Graph Tree views into a single
collapsible sidebar component.

Concept: AU-018 (Sidebar Architecture)
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import TabbedContent, TabPane

from agent_terminal_ui.widgets.graph_tree import GraphTree
from agent_terminal_ui.widgets.tools_sidebar import ToolsSidebar
from agent_terminal_ui.widgets.workflow import WorkflowSidebar


class SideBar(Vertical):
    """Unified sidebar combining plan, workflow, and graph views.

    Provides a tabbed interface for switching between different
    sidebar views. Can be toggled on/off with Ctrl+B.
    """

    DEFAULT_CSS = """
    SideBar {
        width: 30%;
        min-width: 28;
        max-width: 50;
        border-left: solid $primary 30%;
        background: $surface;
        padding: 0;
    }

    SideBar.-hidden {
        display: none;
    }
    """

    def compose(self) -> ComposeResult:
        """Compose the sidebar layout."""
        with TabbedContent(initial="workflow-tab", id="sidebar-tabs"):
            with TabPane("Workflow", id="workflow-tab"):
                yield WorkflowSidebar()
            with TabPane("Graph", id="graph-tab"):
                yield GraphTree("Swarm", id="agent-graph")
            with TabPane("Skills", id="skills-tab"):
                yield ToolsSidebar()

    def toggle(self) -> None:
        """Toggle sidebar visibility."""
        self.toggle_class("-hidden")
