"""Operator installation and contributor documentation contracts."""

import ast
import os
import re
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def check_installation(readme: str) -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    command = next(iter(project["scripts"]))
    installation = readme.split("## Installation\n", 1)[1].split("\n## ", 1)[0]
    minimum = project["requires-python"].removeprefix(">=")
    assert f"Python {minimum} or newer" in installation
    assert "uv sync --frozen" in installation
    assert f"uv run --frozen {command} --help" in installation
    assert "not an Arbora server" in installation
    overview = readme.split("## Overview\n", 1)[1].split("\n## ", 1)[0]
    assert "A2A" in overview and "Arbora runs separately" in overview


@pytest.mark.spec("TUI-RUNTIME-R015.11", "TUI-RUNTIME-R015.14")
def test_operator_installation_documentation() -> None:
    check_installation((ROOT / "README.md").read_text())


@pytest.mark.spec("TUI-RUNTIME-R015.11", "TUI-RUNTIME-R015.14")
@pytest.mark.parametrize("old,new", [
    ("## Installation", "## Missing installation"),
    ("uv sync --frozen", "uv sync"),
    ("uv run --frozen agent-terminal-ui --help", "uv run --frozen missing-command --help"),
    ("Python 3.12 or newer", "Python 3.9 or newer"),
    ("Arbora runs separately", "Arbora is bundled"),
])
def test_installation_rejects_missing_or_incorrect_instructions(old: str, new: str) -> None:
    readme = (ROOT / "README.md").read_text()
    assert old in readme
    with pytest.raises((AssertionError, IndexError)):
        check_installation(readme.replace(old, new))


def check_contributor_guide(guide: str) -> None:
    assert "uv sync --frozen --extra test" in guide
    assert "uv run --frozen --extra test pytest tests/test_source_quality.py -q" in guide
    assert "uvx --from pre-commit==4.6.0 pre-commit run --all-files" in guide
    rows = re.findall(r"\| `([^`]+)` \| ([^|]+) \|", guide)
    paths = {path for path, _ in rows}
    assert {"agent_terminal_ui/terminal_ui.py", "agent_terminal_ui/client.py", "tests/", "specs/terminal-runtime/"} <= paths
    for path, responsibility in rows:
        assert (ROOT / path).exists(), path
        assert len(responsibility.split()) >= 3


@pytest.mark.spec("TUI-RUNTIME-R015.17")
def test_contributor_guide_tools_commands_and_source_map() -> None:
    check_contributor_guide((ROOT / "CONTRIBUTING.md").read_text())


@pytest.mark.spec("TUI-RUNTIME-R015.17")
@pytest.mark.parametrize("old,new", [
    ("--extra test", "--all-groups"),
    ("pre-commit==4.6.0", "missing-tool"),
    ("agent_terminal_ui/client.py", "agent_terminal_ui/missing.py"),
])
def test_contributor_guide_rejects_broken_setup_and_source_paths(old: str, new: str) -> None:
    guide = (ROOT / "CONTRIBUTING.md").read_text()
    with pytest.raises(AssertionError):
        check_contributor_guide(guide.replace(old, new))


@pytest.mark.spec("TUI-RUNTIME-R015.14")
def test_locked_install_refuses_a_checkout_without_its_lockfile(tmp_path: Path) -> None:
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("uv is required for the locked-install counterexample")
    assert uv is not None
    (tmp_path / "pyproject.toml").write_text((ROOT / "pyproject.toml").read_text())
    result = subprocess.run(
        [uv, "sync", "--frozen", "--offline", "--project", str(tmp_path)],
        cwd=tmp_path, capture_output=True, text=True, timeout=20,
        env={**os.environ, "UV_PROJECT_ENVIRONMENT": str(tmp_path / "env"), "UV_PYTHON_DOWNLOADS": "never"},
    )
    assert result.returncode != 0
    assert "lockfile" in result.stderr.lower()


def check_operator_entries(readme: str) -> None:

    source = ast.parse((ROOT / "agent_terminal_ui/terminal_ui.py").read_text())
    flags = {node.args[0].value for node in ast.walk(source)
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
             and node.func.attr == "add_argument" and node.args
             and isinstance(node.args[0], ast.Constant)
             and isinstance(node.args[0].value, str)}
    usage = readme.split("## Usage\n", 1)[1].split("\n## ", 1)[0]
    assert all(f"`{flag}`" in usage or f" {flag} " in usage for flag in flags)
    assert "\nagent-terminal-ui\n" in usage
    assert "agent-terminal-ui --headless --prompt" in usage
    assert "agent-terminal-ui --observe-task TASK_ID" in usage
    assert "cargo run --locked --manifest-path native/agent-terminal-ui/Cargo.toml" in usage
    assert "docker run --rm -e AGENT_URL=" in usage


@pytest.mark.spec("TUI-RUNTIME-R015.12")
def test_readme_operator_entry_points() -> None:
    check_operator_entries((ROOT / "README.md").read_text())


@pytest.mark.spec("TUI-RUNTIME-R015.12")
@pytest.mark.parametrize("entry", ["--observe-task", "--mode", "cargo run", "docker run", "--headless"])
def test_readme_rejects_missing_operator_entries(entry: str) -> None:
    with pytest.raises(AssertionError):
        check_operator_entries((ROOT / "README.md").read_text().replace(entry, "missing-entry"))


def check_documentation_links(readme: str) -> None:
    links = set(re.findall(r"\]\((docs/[^)#]+)(?:#[^)]*)?\)", readme))
    assert {f"docs/{name}.md" for name in ("architecture", "features", "configuration", "session_management", "agent_view", "goal_command")} <= links
    assert all((ROOT / link).is_file() for link in links)


@pytest.mark.spec("TUI-RUNTIME-R015.16")
def test_readme_links_existing_detailed_documentation() -> None:
    check_documentation_links((ROOT / "README.md").read_text())


@pytest.mark.spec("TUI-RUNTIME-R015.16")
@pytest.mark.parametrize("old,new", [("docs/configuration.md", "docs/missing.md"), ("docs/goal_command.md", "https://example.invalid/goal")])
def test_readme_rejects_broken_or_missing_documentation_links(old: str, new: str) -> None:
    with pytest.raises(AssertionError):
        check_documentation_links((ROOT / "README.md").read_text().replace(old, new))
