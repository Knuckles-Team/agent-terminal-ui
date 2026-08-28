from __future__ import annotations

from typing import Any

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Input, Tree


def _item_matches_filter(item: dict[str, Any], filter_text: str, source: str) -> bool:
    """Case-insensitive filter over an item's name/description/source."""
    if not filter_text:
        return True
    n = item.get("name", "")
    d = item.get("description", "")
    text_to_search = f"{n} {d} {source}".lower()
    return filter_text.lower() in text_to_search


def _group_by_source(
    data: list[dict[str, Any]], filter_text: str
) -> dict[str, list[dict[str, Any]]]:
    """Group tools/skills by ``source_name``, applying `filter_text` first."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in data:
        source = item.get("source_name") or "Unknown"
        if not _item_matches_filter(item, filter_text, source):
            continue
        grouped.setdefault(source, []).append(item)
    return grouped


def _source_group_label(source: str, items: list[dict[str, Any]]) -> Text:
    """The tree label for one source group (skill-folder vs. MCP-server icon)."""
    is_skill = any(i.get("type") == "skill" for i in items)
    if is_skill:
        return Text.from_markup(f"📁 [bold cyan]{source}[/] [dim](Skill Folder)[/dim]")
    return Text.from_markup(f"🔌 [bold blue]{source}[/] [dim](MCP Server)[/dim]")


def _item_leaf_label(item: dict[str, Any]) -> Text:
    """The tree label for one leaf item (a tool or a skill)."""
    name = item.get("name", "Unknown")
    desc = item.get("description", "")

    if item.get("type") == "skill":
        label = Text.from_markup(f" 📄 [green]{name}[/]")
    else:
        label = Text.from_markup(f" ⚙️ [yellow]{name}[/]")

    if desc:
        label.append(f" - {desc[:40]}...", style="dim")
    return label


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
        except Exception as e:
            # log or ignore safely. A simple print or notify works.
            try:
                self.app.notify(f"Failed to fetch tools: {e}", severity="warning")
            except Exception:
                pass  # nosec B110

    def _populate_tree(self, data: list[dict[str, Any]], filter_text: str = "") -> None:
        """Populate the tree with the filtered tools/skills."""
        tree = self.query_one("#tools-tree", Tree)
        tree.clear()

        # Group by source (mcp_server for tools, category/folder for skills)
        grouped = _group_by_source(data, filter_text)

        for source, items in sorted(grouped.items()):
            source_node = tree.root.add(_source_group_label(source, items), expand=True)
            for item in sorted(items, key=lambda x: x.get("name", "")):
                source_node.add(_item_leaf_label(item), data=item)

    async def on_input_changed(self, event: Input.Changed) -> None:
        """Filter the tree when search input changes."""
        if event.input.id == "tools-search":
            self._populate_tree(self._all_capabilities, filter_text=event.value)
