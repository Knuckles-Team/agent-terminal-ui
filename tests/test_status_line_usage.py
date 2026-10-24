"""Supporting display regressions for TUI-RUNTIME-R012.6.2, not full acceptance."""

import pytest
from textual.app import App, ComposeResult
from textual.widgets import Static

from agent_terminal_ui.app import AgentApp, AgentEventReceived
from agent_terminal_ui.tui.status_line import StatusLine

pytestmark = pytest.mark.asyncio

UNAVAILABLE = "usage unavailable"


class StatusLineApp(App):
    """Mount the production status line without a network client."""

    def compose(self) -> ComposeResult:
        yield StatusLine()


async def test_status_line_starts_unavailable() -> None:
    app = StatusLineApp()
    async with app.run_test():
        assert str(app.query_one("#status-tokens", Static).render()) == UNAVAILABLE


@pytest.mark.parametrize(
    "usage, expected",
    [
        ({}, UNAVAILABLE),
        (None, UNAVAILABLE),
        ([], UNAVAILABLE),
        ("invalid", UNAVAILABLE),
        ({"total_tokens": None, "estimated_cost_usd": None}, UNAVAILABLE),
        ({"total_tokens": 0, "estimated_cost_usd": 0}, "0 tokens ($0.0000)"),
        ({"total_tokens": 0, "estimated_cost_usd": 0.0}, "0 tokens ($0.0000)"),
        ({"total_tokens": 500, "estimated_cost_usd": 0.005}, "500 tokens ($0.0050)"),
        (
            {"total_tokens": 12345, "estimated_cost_usd": 0.125},
            "12.3K tokens ($0.1250)",
        ),
        ({"total_tokens": 42}, "42 tokens (cost unavailable)"),
        ({"estimated_cost_usd": 0.25}, "tokens unavailable ($0.2500)"),
        (
            {"total_tokens": 0, "estimated_cost_usd": None},
            "0 tokens (cost unavailable)",
        ),
        (
            {"total_tokens": None, "estimated_cost_usd": 0},
            "tokens unavailable ($0.0000)",
        ),
    ],
)
async def test_status_line_replaces_usage(usage: object, expected: str) -> None:
    app = StatusLineApp()
    async with app.run_test():
        status = app.query_one(StatusLine)
        widget = status.query_one("#status-tokens", Static)
        status.update_usage({"total_tokens": 100, "estimated_cost_usd": 0.25})
        assert str(widget.render()) == "100 tokens ($0.2500)"
        status.update_usage(usage)
        assert str(widget.render()) == expected


@pytest.mark.parametrize(
    "invalid",
    [
        None,
        True,
        False,
        -1,
        float("nan"),
        float("inf"),
        -float("inf"),
        "0",
        [],
        {},
        10**400,
    ],
)
async def test_status_line_validates_fields_independently(invalid: object) -> None:
    app = StatusLineApp()
    async with app.run_test():
        status = app.query_one(StatusLine)
        widget = status.query_one("#status-tokens", Static)
        status.update_usage({"total_tokens": invalid, "estimated_cost_usd": 0})
        assert str(widget.render()) == "tokens unavailable ($0.0000)"
        status.update_usage({"total_tokens": 0, "estimated_cost_usd": invalid})
        assert str(widget.render()) == "0 tokens (cost unavailable)"


@pytest.mark.parametrize("tokens", [0.0, 1.5])
async def test_status_line_requires_integer_tokens(tokens: float) -> None:
    app = StatusLineApp()
    async with app.run_test():
        status = app.query_one(StatusLine)
        status.update_usage({"total_tokens": tokens, "estimated_cost_usd": 1})
        assert (
            str(status.query_one("#status-tokens", Static).render())
            == "tokens unavailable ($1.0000)"
        )


@pytest.mark.parametrize(
    "event_type, field", [("usage", "data"), ("turn_end", "usage")]
)
async def test_mounted_usage_events_clear_stale_values(
    app: AgentApp, event_type: str, field: str
) -> None:
    async with app.run_test(size=(120, 35)):
        widget = app.query_one("#status-tokens", Static)
        unavailable_values: tuple[object, ...] = (
            {},
            None,
            [],
            {"total_tokens": None, "estimated_cost_usd": None},
        )
        for unavailable in unavailable_values:
            await app.on_agent_event_received(
                AgentEventReceived(
                    {
                        "type": event_type,
                        field: {"total_tokens": 100, "estimated_cost_usd": 0.25},
                    }
                )
            )
            assert str(widget.render()) == "100 tokens ($0.2500)"
            await app.on_agent_event_received(
                AgentEventReceived({"type": event_type, field: unavailable})
            )
            assert str(widget.render()) == UNAVAILABLE
