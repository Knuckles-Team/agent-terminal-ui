"""Acceptance checks for migrated source-quality requirements."""

from pathlib import Path

import pytest

from agent_terminal_ui.client import client_from_environment

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
