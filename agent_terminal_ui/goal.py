"""Lightweight goal specification for the ``/goal`` command.

Parses ``/goal`` input into a structured spec and renders the autonomous-goal
system prompt suffix. This is a frontend-local mirror of the backend
``agent_utilities.models.goal.GoalSpec`` parsing surface, kept dependency-free so
the terminal UI never imports the heavy ``agent_utilities`` package (and the KG
engine it drags in) just to start a goal. The backend remains the source of truth
for KG-native goal persistence; the frontend only needs to parse input and build
the prompt before submitting it over HTTP.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_UNTIL_WITHOUT = re.compile(r"^(.+?)\s+until\s+(.+?)\s+without\s+(.+)$", re.IGNORECASE)
_UNTIL = re.compile(r"^(.+?)\s+until\s+(.+)$", re.IGNORECASE)
_CMD_PATTERNS = (
    re.compile(r"(\w+\s+\w+)\s+exits?\s+(\d+)", re.IGNORECASE),
    re.compile(r"(\w+)\s+(?:returns?|passes?|succeeds?)", re.IGNORECASE),
)


@dataclass
class GoalSpec:
    """Structured ``/goal`` objective parsed from raw user input."""

    objective: str = ""
    end_state: str = ""
    constraints: list[str] = field(default_factory=list)
    validation_cmd: str = ""
    max_iterations: int = 20
    auto_approve: bool = True
    session_id: str = ""
    raw_input: str = ""

    @classmethod
    def parse_goal_input(cls, raw_input: str) -> GoalSpec:
        """Parse a raw ``/goal`` string into a structured spec.

        Supports ``<objective> until <end_state> without <constraints>``,
        ``<objective> until <end_state>``, and the bare ``<objective>`` form.
        """
        text = raw_input.strip()
        if text.lower().startswith("/goal"):
            text = text[5:].strip()

        objective = text
        end_state = ""
        constraints: list[str] = []
        validation_cmd = ""

        until_without = _UNTIL_WITHOUT.match(text)
        if until_without:
            objective = until_without.group(1).strip()
            end_state = until_without.group(2).strip()
            constraints = [c.strip() for c in until_without.group(3).strip().split(",")]
        else:
            until_match = _UNTIL.match(text)
            if until_match:
                objective = until_match.group(1).strip()
                end_state = until_match.group(2).strip()

        for pattern in _CMD_PATTERNS:
            cmd_match = pattern.search(end_state or objective)
            if cmd_match:
                validation_cmd = cmd_match.group(1)
                break

        return cls(
            objective=objective,
            end_state=end_state,
            constraints=constraints,
            validation_cmd=validation_cmd,
            raw_input=raw_input,
        )

    def to_system_prompt(self) -> str:
        """Render the autonomous-goal system prompt suffix."""
        parts = [
            "## Autonomous Goal Mode",
            f"**Objective:** {self.objective}",
        ]
        if self.end_state:
            parts.append(f"**Success Criteria:** {self.end_state}")
        if self.constraints:
            parts.append("**Constraints:**")
            parts.extend(f"  - Do NOT {constraint}" for constraint in self.constraints)
        if self.validation_cmd:
            parts.append(
                f"**Validation:** Run `{self.validation_cmd}` to check completion."
            )
        parts.extend(
            [
                "",
                "Work autonomously toward this goal. After each action:",
                "1. Evaluate progress toward the success criteria",
                "2. If not complete, plan and execute the next step",
                "3. If the validation command is specified, run it to check",
                "4. Report completion only when criteria are fully met",
                f"5. Stop after {self.max_iterations} iterations if not complete",
            ]
        )
        return "\n".join(parts)
