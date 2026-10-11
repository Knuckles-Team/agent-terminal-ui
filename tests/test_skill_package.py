from pathlib import Path

import pytest

import agent_terminal_ui

SKILL = Path(agent_terminal_ui.__file__).parent / "skills" / "agent-terminal-ui-development" / "SKILL.md"


@pytest.mark.spec("TUI-RUNTIME-R003")
def test_development_skill_packaged():
    text = SKILL.read_text()
    assert "Rapid delivery: the 5-minute contract" in text
    pyproject = (Path(__file__).parents[1] / "pyproject.toml").read_text()
    assert "skills/**/*" in pyproject
