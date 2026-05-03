from __future__ import annotations

from typing import Any

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Input, Tree


class ToolsSidebar(Vertical):
    """Sidebar widget for searching and displaying loaded Skills and Tools."""

    DEFAULT_CSS = """
    ToolsSidebar {
        width: 100%;
        height: 100%;
    }
    #tools-search {
        dock: top;
        margin: 1 1;
        width: 100%;
    }
    #tools-tree {
        width: 100%;
        height: 100%;
    }
    """

    def compose(self) -> ComposeResult:
        yield Input(placeholder="Search skills & tools...", id="tools-search")
        tree: Tree[dict[str, Any]] = Tree("Capabilities", id="tools-tree")
        tree.root.expand()
        yield tree

    def on_mount(self) -> None:
        """Fetch tools on mount."""
        self._all_capabilities: list[dict[str, Any]] = []
        self._fetch_tools()

    @work(exclusive=True)
    async def _fetch_tools(self) -> None:
        """Fetch tools and skills from the backend."""
        try:
            # The app instance should have an agent_client attribute
            client = self.app.agent_client  # type: ignore
            data = await client.list_tools()
            self._all_capabilities = data
            self.app.call_from_thread(self._populate_tree, data)
        except Exception:
            pass

    def _populate_tree(self, data: list[dict[str, Any]], filter_text: str = "") -> None:
        """Populate the tree with the filtered tools/skills."""
        tree = self.query_one("#tools-tree", Tree)
        tree.clear()

        # Group by source (mcp_server for tools, category/folder for skills)
        grouped: dict[str, list[dict[str, Any]]] = {}
        for item in data:
            source = item.get("source_name") or "Unknown"

            # Simple case-insensitive filter
            if filter_text:
                text_to_search = f"{item.get('name', '')} {item.get('description', '')} {source}".lower()
                if filter_text.lower() not in text_to_search:
                    continue

            if source not in grouped:
                grouped[source] = []
            grouped[source].append(item)

        for source, items in sorted(grouped.items()):
            # Determine if it's a skill source or tool source based on the first item
            is_skill = any(i.get("type") == "skill" for i in items)

            if is_skill:
                source_label = Text.from_markup(
                    f"📁 [bold cyan]{source}[/] [dim](Skill Folder)[/dim]"
                )
            else:
                source_label = Text.from_markup(
                    f"🔌 [bold blue]{source}[/] [dim](MCP Server)[/dim]"
                )

            source_node = tree.root.add(source_label, expand=True)

            for item in sorted(items, key=lambda x: x.get("name", "")):
                name = item.get("name", "Unknown")
                desc = item.get("description", "")

                # Visual distinction between skill and tool
                if item.get("type") == "skill":
                    label = Text.from_markup(f" 📄 [green]{name}[/]")
                else:
                    label = Text.from_markup(f" ⚙️ [yellow]{name}[/]")

                if desc:
                    label.append(f" - {desc[:40]}...", style="dim")

                source_node.add(label, data=item)

    async def on_input_changed(self, event: Input.Changed) -> None:
        """Filter the tree when search input changes."""
        if event.input.id == "tools-search":
            self._populate_tree(self._all_capabilities, filter_text=event.value)
