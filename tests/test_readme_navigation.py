"""README navigation and architecture match the shipped frontend boundaries."""

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def section(readme: str, name: str) -> str:
    return readme.split(f"## {name}\n", 1)[1].split("\n## ", 1)[0]


def check_navigation(readme: str) -> None:
    headings = re.findall(r"^## (.+)$", readme, re.MULTILINE)
    expected = {heading.lower().replace(" ", "-") for heading in headings if heading != "Contents"}
    links = re.findall(r"\]\(#([^)]*)\)", section(readme, "Contents"))
    assert set(links) == expected
    assert len(links) == len(expected)
    assert section(readme, "Usage").count("### Native turn usage") == 1
    assert "Native turn usage" not in section(readme, "License")


@pytest.mark.spec("TUI-RUNTIME-R015.13")
def test_readme_navigation_reaches_each_top_level_section() -> None:
    check_navigation((ROOT / "README.md").read_text())


@pytest.mark.spec("TUI-RUNTIME-R015.13")
@pytest.mark.parametrize("old,new", [
    ("- [Installation](#installation)\n", ""),
    ("[Usage](#usage)", "[Usage](#missing-usage)"),
    ("## Development", "## Developer setup"),
    ("- [Overview](#overview)", "- [Overview](#overview)\n- [Overview](#overview)"),
])
def test_navigation_rejects_missing_stale_and_duplicate_targets(old: str, new: str) -> None:
    text = (ROOT / "README.md").read_text()
    assert old in text
    with pytest.raises(AssertionError):
        check_navigation(text.replace(old, new))


def check_architecture(readme: str) -> None:
    architecture = section(readme, "Architecture")
    required = [
        "Both paths use AgentClient for served requests.",
        "Arbora runs in a separate process.",
        "Headless mode creates no Textual widget tree.",
        "A2A JSON-RPC at `/a2a`",
        "`message/send`", "`tasks/get`", "`--observe-task`",
        "`AGENT_URL`", "`AGENT_BEARER_TOKEN`",
        "does not import the heavy `agent_utilities` backend",
        "separate Rust implementation",
    ]
    for claim in required:
        assert claim in architecture, claim
    paths = set(re.findall(r"\]\(([^)]+)\)", architecture))
    assert paths == {
        "agent_terminal_ui/terminal_ui.py", "agent_terminal_ui/app.py",
        "agent_terminal_ui/headless.py", "agent_terminal_ui/client.py",
        "agent_terminal_ui/screens/", "agent_terminal_ui/widgets/",
        "native/agent-terminal-ui/",
    }
    assert all((ROOT / path).exists() for path in paths)
    for module in ("app.py", "headless.py"):
        tree = ast.parse((ROOT / "agent_terminal_ui" / module).read_text())
        calls = {node.func.id for node in ast.walk(tree)
                 if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
        assert "client_from_environment" in calls


@pytest.mark.spec("TUI-RUNTIME-R015.15")
def test_readme_explains_frontend_entry_paths_and_served_boundary() -> None:
    check_architecture((ROOT / "README.md").read_text())


@pytest.mark.spec("TUI-RUNTIME-R015.15")
@pytest.mark.parametrize("old,new", [
    ("Arbora runs in a separate process.", "Arbora runs inside the frontend."),
    ("Headless mode creates no Textual widget tree.", "Headless mode creates a Textual widget tree."),
    ("A2A JSON-RPC at `/a2a`", "ACP at `/acp`"),
    ("agent_terminal_ui/client.py", "agent_terminal_ui/missing.py"),
    ("separate Rust implementation", "shared Python implementation"),
])
def test_architecture_rejects_wrong_transport_boundaries_and_paths(old: str, new: str) -> None:
    text = (ROOT / "README.md").read_text()
    assert old in text
    with pytest.raises(AssertionError):
        check_architecture(text.replace(old, new))
