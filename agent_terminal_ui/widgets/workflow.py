from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Label


class WorkflowSidebar(Vertical):
    """Sidebar to visualize the current agent execution state and graph nodes."""

    DEFAULT_CSS = """
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

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.active_node = "Basic"
        self.nodes = ["Planner", "Researcher", "Programmer", "Architect", "QA"]

    def compose(self) -> ComposeResult:
        yield Label("[bold]Workflow Execution[/bold]")
        with VerticalScroll(id="node-list"):
            for node in self.nodes:
                yield Label(
                    node, id=f"node-{node.lower()}", classes="node-item node-pending"
                )

    def update_state(self, node: str, status: str = "active"):
        """Update the active node in the sidebar."""
        self.active_node = node
        for n in self.nodes:
            widget = self.query_one(f"#node-{n.lower()}", Label)
            if n.lower() == node.lower():
                widget.add_class("node-active")
                widget.remove_class("node-pending")
                widget.update(f"▶ {n}")
            else:
                widget.remove_class("node-active")
                widget.add_class("node-pending")
                widget.update(n)
