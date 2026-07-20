"""Tests for the vendored, dependency-free GoalSpec parser."""

import pytest

from agent_terminal_ui.goal import GoalSpec


@pytest.mark.parametrize(
    "raw,objective,end_state,constraints,validation_cmd",
    [
        (
            "fix failing tests until npm test exits 0 without modifying /auth",
            "fix failing tests",
            "npm test exits 0",
            ["modifying /auth"],
            "npm test",
        ),
        (
            "fix tests until npm test exits 0 without touching db, skipping ci",
            "fix tests",
            "npm test exits 0",
            ["touching db", "skipping ci"],
            "npm test",
        ),
        (
            "refactor the parser until pytest passes",
            "refactor the parser",
            "pytest passes",
            [],
            "pytest",
        ),
        ("add a dark theme", "add a dark theme", "", [], ""),
        (
            "/goal improve docs until mkdocs build succeeds",
            "improve docs",
            "mkdocs build succeeds",
            [],
            "build",
        ),
    ],
)
def test_parse_goal_input(
    raw: str,
    objective: str,
    end_state: str,
    constraints: list[str],
    validation_cmd: str,
) -> None:
    spec = GoalSpec.parse_goal_input(raw)
    assert spec.objective == objective
    assert spec.end_state == end_state
    assert spec.constraints == constraints
    assert spec.validation_cmd == validation_cmd
    assert spec.raw_input == raw


def test_to_system_prompt_includes_sections() -> None:
    spec = GoalSpec.parse_goal_input(
        "fix tests until pytest passes without touching db"
    )
    prompt = spec.to_system_prompt()
    assert "## Autonomous Goal Mode" in prompt
    assert "**Objective:** fix tests" in prompt
    assert "**Success Criteria:** pytest passes" in prompt
    assert "Do NOT touching db" in prompt
    assert "Run `pytest`" in prompt
    assert f"Stop after {spec.max_iterations} iterations" in prompt


def test_defaults() -> None:
    spec = GoalSpec.parse_goal_input("do a thing")
    assert spec.max_iterations == 20
    assert spec.auto_approve is True
    assert spec.session_id == ""
