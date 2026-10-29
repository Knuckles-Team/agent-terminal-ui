"""Opt-in PTY bridge for a disposable, installed Arbora/EG boot fixture.

The fixture owner must keep its admitted run and current plan alive while this
test executes. No provider, registry or read response is replaced here. A caller
may invoke ``exercise_served_current_plan`` directly from its boot qualification.
"""

import json
import os
import uuid
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, Request, build_opener

import pytest

from tests.test_native_public_details_pty import NativeTerminal


def exercise_served_current_plan(
    base_url: str,
    bearer_token: str,
    task_id: str,
    run_id: str,
    context_id: str,
    expected_plan: str,
) -> None:
    """Read a real plan, then reject an invalid disposable bearer."""
    parsed = urlsplit(base_url)
    assert parsed.scheme == "http" and parsed.hostname in {
        "127.0.0.1",
        "localhost",
        "::1",
    }
    assert parsed.username is None and parsed.password is None
    assert bearer_token and task_id and run_id and expected_plan
    assert context_id and len({task_id, run_id, context_id}) == 3
    request = Request(
        f"{base_url.rstrip('/')}/api/v1/registry",
        headers={"Authorization": f"Bearer {bearer_token}"},
    )
    with build_opener(ProxyHandler({})).open(request, timeout=30) as response:
        registry = json.load(response)
    assert "runs.get" in {operation["id"] for operation in registry["ops"]}

    terminal = NativeTerminal(base_url, [], task_id, bearer_token=bearer_token)
    try:
        terminal.wait_until(
            lambda: (
                f"Task ID: {task_id}" in terminal.shown()
                and f"Run ID: {run_id}" in terminal.shown()
                and f"Context ID: {context_id}" in terminal.shown()
                and "State:" in terminal.shown()
            )
        )
        terminal.send(b"i")
        terminal.wait_until(
            lambda: (
                "Current plan revision:" in terminal.shown()
                and expected_plan in terminal.shown()
            )
        )
        assert "Run summary unavailable; current-plan read only" not in terminal.shown()
        terminal.quit()
    finally:
        terminal.close()

    refused = NativeTerminal(
        base_url, [], task_id, bearer_token=f"invalid-{uuid.uuid4().hex}"
    )
    try:
        refused.wait_until(
            lambda: "Arbora task read refused or unavailable" in refused.shown()
        )
        assert expected_plan not in refused.shown()
        assert "Current plan revision:" not in refused.shown()
        refused.quit()
    finally:
        refused.close()


@pytest.mark.spec("TUIG-RUNTIME-R010.8")
def test_installed_arbora_current_plan_read_and_refusal() -> None:
    names = (
        "TUI_SERVED_TEST_URL",
        "TUI_SERVED_TEST_BEARER",
        "TUI_SERVED_TEST_TASK_ID",
        "TUI_SERVED_TEST_RUN_ID",
        "TUI_SERVED_TEST_CONTEXT_ID",
        "TUI_SERVED_TEST_PLAN_TEXT",
    )
    if not os.environ.get("TUI_NATIVE_TEST_BINARY") or not all(
        os.environ.get(name) for name in names
    ):
        pytest.skip(
            "Requires an explicit native binary and a live disposable Arbora fixture"
        )
    exercise_served_current_plan(*(os.environ[name] for name in names))


@pytest.mark.spec("TUIG-RUNTIME-R010.8")
def test_terminal_credentials_are_explicit_not_inherited(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environments: list[dict[str, str]] = []

    class Process:
        def poll(self) -> int:
            return 0

    def launch(*args: object, **kwargs: object) -> Process:
        environment = kwargs["env"]
        assert isinstance(environment, dict)
        environments.append(environment)
        return Process()

    monkeypatch.setenv("TUI_NATIVE_TEST_BINARY", "/unused/fixture-binary")
    monkeypatch.setenv("AGENT_BEARER_TOKEN", "must-not-be-inherited")
    monkeypatch.setenv("NO_PROXY", "wrong.example")
    monkeypatch.setenv("no_proxy", "wrong.example")
    monkeypatch.setattr("tests.test_native_public_details_pty.subprocess.Popen", launch)
    for token in [None, "disposable-fixture-bearer"]:
        terminal = NativeTerminal("http://127.0.0.1:1234", [], bearer_token=token)
        terminal.close()
    assert environments[0]["AGENT_AUTH_MODE"] == "none"
    assert "AGENT_BEARER_TOKEN" not in environments[0]
    assert environments[1]["AGENT_AUTH_MODE"] == "bearer"
    assert environments[1]["AGENT_BEARER_TOKEN"] == "disposable-fixture-bearer"
    assert environments[0]["NO_PROXY"] == "wrong.example"
    assert environments[0]["no_proxy"] == "wrong.example"
    assert environments[1]["NO_PROXY"] == "localhost,127.0.0.1,::1"
    assert environments[1]["no_proxy"] == "localhost,127.0.0.1,::1"
    assert all(env["AGENT_URL"] == "http://127.0.0.1:1234" for env in environments)
