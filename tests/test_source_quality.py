"""Acceptance checks for migrated source-quality requirements."""

import subprocess
from pathlib import Path

import httpx

import pytest

from agent_terminal_ui.client import AgentClient, ArboraOperationError, client_from_environment

EXAMPLE_DEFAULTS = {
    "AGENT_URL": "http://localhost:8000",
    "AGENT_THEME": "tokyo-night",
}


def _example_values(content: str) -> dict[str, str]:
    """Validate inert onboarding defaults without executing shell input."""
    values = {}
    for line in content.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        name, separator, value = line.partition("=")
        assert separator and name not in values
        values[name] = value
    assert values == EXAMPLE_DEFAULTS
    return values


@pytest.mark.spec("TUI-RUNTIME-R015.43")
@pytest.mark.asyncio
async def test_source_quality_43(monkeypatch: pytest.MonkeyPatch) -> None:
    """The real example configures the client without a stored credential."""
    example = Path(__file__).parents[1] / ".env.example"
    values = _example_values(example.read_text())
    monkeypatch.delenv("AGENT_BEARER_TOKEN", raising=False)
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    client = client_from_environment()
    try:
        assert client.base_url == EXAMPLE_DEFAULTS["AGENT_URL"]
        assert "Authorization" not in client._http_client.headers
    finally:
        await client.close()


@pytest.mark.spec("TUI-RUNTIME-R015.43")
@pytest.mark.parametrize(
    "mutation",
    [
        "AGENT_URL=http://localhost:8000\n",
        "AGENT_URL=https://remote.example\nAGENT_THEME=tokyo-night\n",
        "AGENT_URL=http://localhost:8000\nAGENT_THEME=tokyo-night\n"
        "AGENT_BEARER_TOKEN=example-token\n",
        "AGENT_URL=$(hostname)\nAGENT_THEME=tokyo-night\n",
        "AGENT_URL=http://localhost:8000#$(id)\nAGENT_THEME=tokyo-night\n",
        "AGENT_URL=http://localhost:8000\nAGENT_THEME=tokyo-night;id\n",
    ],
)
def test_environment_example_rejects_counterexamples(mutation: str) -> None:
    """Missing defaults, credentials and shell expressions cannot pass."""
    with pytest.raises(AssertionError):
        _example_values(mutation)


ASSESSMENT_HEADING = "## Environment and tool-guard assessment (R015.54)"
HISTORY_REF = "b4e5940acc4b21df406eeb115c0f422b0b084901"
HISTORY_PATH = "plans/spec-source-history/tasks/fix_missing_client_methods.md"


def _check_quick_win_assessment(document: str, suggestion: str, refusal: str) -> None:
    assessment = document.split(ASSESSMENT_HEADING, 1)[1].split("\n## ", 1)[0]
    assert f"{HISTORY_REF}/{HISTORY_PATH}" in assessment
    assert suggestion in assessment
    assert "The source does not identify shared development hooks" in assessment
    assert "Environment example: available under R015.43" in assessment
    assert "Runtime tool guards: refusal only" in assessment
    assert refusal in assessment
    assert "This assessment does not close any of these requirements or enable tool effects" in assessment
    assert all(owner in assessment for owner in ("R001.3", "R001.5", "R011.4", "R011.5", "R002.8.4"))


@pytest.mark.spec("TUI-RUNTIME-R015.54")
@pytest.mark.asyncio
async def test_source_quality_54(monkeypatch: pytest.MonkeyPatch) -> None:
    """Compare the assessment with its original source and actual client refusal."""
    root = Path(__file__).resolve().parents[1]
    historical = subprocess.run(
        ["git", "show", f"{HISTORY_REF}:{HISTORY_PATH}"],
        cwd=root, capture_output=True, text=True, timeout=10, check=True,
    ).stdout
    suggestion = next(line.removeprefix("4. ") for line in historical.splitlines() if line.startswith("4. Consider"))
    document = (root / "specs/terminal-runtime/test-spec.md").read_text()
    await test_source_quality_43(monkeypatch)
    requests: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"ok": True, "result": {}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(record)) as transport:
        client = AgentClient(base_url="http://localhost:8000", bearer_token="test-caller")
        await client._http_client.aclose()
        client._http_client = transport
        for operation in ("approvals.grant", "APPROVALS.GRANT"):
            with pytest.raises(ArboraOperationError) as refused:
                await client.invoke_op(operation, {})
            _check_quick_win_assessment(document, suggestion, refused.value.code)
        with pytest.raises(ArboraOperationError) as refused:
            await client.confirm_plan(plan_ref="unsigned-plan", op="fleet.status", params={})
        _check_quick_win_assessment(document, suggestion, refused.value.code)
    assert requests == []


@pytest.mark.spec("TUI-RUNTIME-R015.54")
@pytest.mark.parametrize("old,new", [
    ("The source does not identify shared development hooks", "The source specifies shared development hooks"),
    ("Runtime tool guards: refusal only", "Runtime tool guards: fully authorized"),
    ("APPROVAL_UNAVAILABLE", "APPROVAL_GRANTED"),
    ("R011.4 and R011.5", "No remaining workspace obligations"),
    ("This assessment does not close any of these requirements or enable tool effects", "All tool effects are authorized"),
])
def test_quick_win_assessment_rejects_false_completion(old: str, new: str) -> None:
    document = (Path(__file__).resolve().parents[1] / "specs/terminal-runtime/test-spec.md").read_text()
    suggestion = "Consider implementing quick wins (.env.example, tool guards)"
    assert old in document
    with pytest.raises(AssertionError):
        _check_quick_win_assessment(document.replace(old, new), suggestion, "APPROVAL_UNAVAILABLE")
