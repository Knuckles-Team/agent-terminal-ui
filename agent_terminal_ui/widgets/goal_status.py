"""Goal status widget for the terminal UI.

Displays live progress of an active ``/goal`` execution including
iteration count, current step, and validation output.

Concept: ORCH-5.0 (Autonomous Goal Loop)
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.reactive import var
from textual.widgets import Label, ProgressBar, Static


class GoalStatusWidget(Static):
    """Live dashboard for an active goal execution.

    Shows iteration progress, current action, and validation status
    inline within the main conversation view.
    """

    DEFAULT_CSS = """
    GoalStatusWidget {
        height: auto;
        max-height: 6;
        padding: 0 1;
        margin: 0 0 1 0;
        background: $primary 10%;
        border: solid $primary 30%;
    }

    GoalStatusWidget #goal-header {
        text-style: bold;
        color: $primary;
    }

    GoalStatusWidget #goal-action {
        color: $text;
        text-style: italic;
    }

    GoalStatusWidget #goal-validation {
        color: $success;
    }

    GoalStatusWidget ProgressBar {
        margin: 0 1;
    }
    """

    objective: var[str] = var("")
    current_iteration: var[int] = var(0)
    max_iterations: var[int] = var(20)
    current_action: var[str] = var("")
    validation_result: var[str] = var("")
    is_active: var[bool] = var(False)

    def compose(self) -> ComposeResult:
        yield Label("🎯 Goal: (none)", id="goal-header")
        with Horizontal():
            yield ProgressBar(total=20, show_percentage=True, id="goal-progress")
        yield Label("", id="goal-action")
        yield Label("", id="goal-validation")

    def update_goal(
        self,
        objective: str = "",
        iteration: int = 0,
        max_iterations: int = 20,
        action: str = "",
        validation: str = "",
        active: bool = True,
    ) -> None:
        """Update the goal status display.

        Args:
            objective: The goal objective text.
            iteration: Current iteration number.
            max_iterations: Maximum iterations allowed.
            action: Current action description.
            validation: Last validation output.
            active: Whether the goal is actively running.
        """
        self.objective = objective
        self.current_iteration = iteration
        self.max_iterations = max_iterations
        self.current_action = action
        self.validation_result = validation
        self.is_active = active

        header = self.query_one("#goal-header", Label)
        progress = self.query_one("#goal-progress", ProgressBar)
        action_label = self.query_one("#goal-action", Label)
        validation_label = self.query_one("#goal-validation", Label)

        status_icon = "🟢" if active else "✅"
        header.update(
            f"{status_icon} Goal: {objective[:50]}"
            + ("..." if len(objective) > 50 else "")
            + f" [{iteration}/{max_iterations}]"
        )

        progress.update(total=max_iterations, progress=iteration)

        if action:
            action_label.update(f"  → {action[:80]}")
        else:
            action_label.update("")

        if validation:
            validation_label.update(f"  ✓ {validation[:80]}")
        else:
            validation_label.update("")

    def clear_goal(self) -> None:
        """Clear the goal status display."""
        self.is_active = False
        self.query_one("#goal-header", Label).update("🎯 Goal: (none)")
        self.query_one("#goal-progress", ProgressBar).update(total=1, progress=0)
        self.query_one("#goal-action", Label).update("")
        self.query_one("#goal-validation", Label).update("")
