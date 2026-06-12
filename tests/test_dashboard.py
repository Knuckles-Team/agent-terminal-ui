"""Tests for the HTTP-backed service dashboard data handling."""

from unittest.mock import MagicMock

from agent_terminal_ui.screens.dashboard import DashboardScreen


def _screen_with_cards(*service_ids: str) -> DashboardScreen:
    screen = DashboardScreen()
    for sid in service_ids:
        screen._cards[sid] = MagicMock()
    screen._available = True
    return screen


def test_apply_data_handles_dict_fields() -> None:
    """Backend ``/api/dashboard`` returns fields as a {key: value} dict."""
    screen = _screen_with_cards("portainer-1")
    screen._apply_data(
        {
            "portainer-1": {
                "status": "ok",
                "fields": {"containers": 12, "stacks": 3},
                "error": None,
            }
        }
    )
    card = screen._cards["portainer-1"]
    card.update_data.assert_called_once()
    kwargs = card.update_data.call_args.kwargs
    assert kwargs["status"] == "ok"
    assert ("containers", "12") in kwargs["fields"]


def test_apply_data_handles_list_fields_and_errors() -> None:
    """Also tolerate a list-of-{label,value} field shape and error status."""
    screen = _screen_with_cards("svc")
    screen._apply_data(
        {
            "svc": {
                "status": "error",
                "fields": [{"label": "Up", "value": "no"}],
                "error": "unreachable",
            },
            "unknown-service": {"status": "ok", "fields": {}},  # no card; ignored
        }
    )
    card = screen._cards["svc"]
    kwargs = card.update_data.call_args.kwargs
    assert kwargs["status"] == "error"
    assert kwargs["error"] == "unreachable"
    assert ("Up", "no") in kwargs["fields"]
