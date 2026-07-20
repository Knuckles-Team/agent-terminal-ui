"""Tests for the temporal graph scrubber widget (TUI-22).

Covers the pure query/expiry helpers and a Pilot render smoke test that the
widget composes, accepts an AS OF timestamp, and dims expired edges.
"""

from __future__ import annotations

from textual.app import App, ComposeResult

from agent_terminal_ui.widgets.graph_tree import GraphTree
from agent_terminal_ui.widgets.temporal_graph import (
    BASE_UQL,
    TemporalGraph,
    is_edge_expired,
    with_as_of,
)


class TestTemporalHelpers:
    def test_with_as_of_appends_operator(self) -> None:
        assert (
            with_as_of("MATCH (n) RETURN n", "2026-06-01T00:00:00Z")
            == "MATCH (n) RETURN n |> AS OF @2026-06-01T00:00:00Z"
        )

    def test_with_as_of_strips_whitespace(self) -> None:
        assert with_as_of("  MATCH (n)  ", "T").endswith("MATCH (n) |> AS OF @T")

    def test_edge_expired_when_valid_until_before_ts(self) -> None:
        edge = {"source": "a", "target": "b", "valid_until": "2026-05-01T00:00:00Z"}
        assert is_edge_expired(edge, "2026-06-01T00:00:00Z") is True

    def test_edge_live_when_valid_until_after_ts(self) -> None:
        edge = {"source": "a", "target": "b", "valid_until": "2026-07-01T00:00:00Z"}
        assert is_edge_expired(edge, "2026-06-01T00:00:00Z") is False

    def test_edge_live_when_no_valid_until(self) -> None:
        assert is_edge_expired({"source": "a", "target": "b"}, "2026-06-01") is False


class _Harness(App):
    """Minimal host mounting the temporal graph widget in isolation."""

    def compose(self) -> ComposeResult:
        yield TemporalGraph(id="temporal-graph")


async def test_temporal_graph_composes_and_renders_expired() -> None:
    async with _Harness().run_test() as pilot:
        widget = pilot.app.query_one("#temporal-graph", TemporalGraph)
        assert isinstance(widget.tree, GraphTree)

        nodes = [{"id": "a", "name": "Alpha"}, {"id": "b", "name": "Beta"}]
        edges = [
            {"source": "a", "target": "b", "type": "LINKS"},
            {
                "source": "a",
                "target": "b",
                "type": "OLD_LINK",
                "valid_until": "2026-01-01T00:00:00Z",
            },
        ]
        widget.render_as_of(nodes, edges, "2026-06-01T00:00:00Z")
        await pilot.pause()

        # Root re-labelled to the AS OF instant; two node children present.
        assert "2026-06-01" in str(widget.tree.root.label)
        node_children = widget.tree.root.children
        assert len(node_children) == 2

        # The expired edge leaf carries the "(expired)" tag; the live one does not.
        all_leaf_labels = [
            str(leaf.label) for parent in node_children for leaf in parent.children
        ]
        assert any("(expired)" in lbl for lbl in all_leaf_labels)
        assert any("OLD_LINK" in lbl for lbl in all_leaf_labels)


async def test_temporal_graph_input_emits_as_of_query() -> None:
    captured: list[tuple[str, str]] = []

    class _CaptureHarness(App):
        def compose(self) -> ComposeResult:
            yield TemporalGraph(id="temporal-graph")

        def on_temporal_graph_as_of_requested(
            self, event: TemporalGraph.AsOfRequested
        ) -> None:
            captured.append((event.iso_ts, event.query))

    async with _CaptureHarness().run_test() as pilot:
        ts_input = pilot.app.query_one("#temporal-ts-input")
        ts_input.value = "2026-06-01T00:00:00Z"
        ts_input.focus()
        await pilot.press("enter")
        await pilot.pause()

    assert captured, "AsOfRequested was not emitted on submit"
    iso_ts, query = captured[-1]
    assert iso_ts == "2026-06-01T00:00:00Z"
    assert query == with_as_of(BASE_UQL, "2026-06-01T00:00:00Z")
    assert "|> AS OF @" in query
