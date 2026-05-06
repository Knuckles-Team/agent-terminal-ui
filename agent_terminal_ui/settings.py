"""TOML-backed settings manager for the Agent Terminal UI.

Provides a schema-driven settings system that persists to disk,
with defaults, validation, and reactive access.

Concept: AU-018 (Settings Management)
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_SETTINGS_DIR = Path.home() / ".config" / "agent-terminal-ui"
DEFAULT_SETTINGS_FILE = DEFAULT_SETTINGS_DIR / "settings.toml"


@dataclass
class SettingDef:
    """Definition for a single setting."""

    key: str
    title: str
    help: str = ""
    type: str = "string"  # string, boolean, integer, choices
    default: Any = None
    choices: list[str] | None = None
    editable: bool = True


# Settings schema
SETTINGS_SCHEMA: list[SettingDef] = [
    SettingDef(
        key="theme",
        title="Theme",
        help="Textual built-in theme name",
        type="choices",
        default="tokyo-night",
        choices=[
            "textual-dark",
            "textual-light",
            "tokyo-night",
            "monokai",
            "dracula",
            "catppuccin-mocha",
            "nord",
            "gruvbox",
            "textual-ansi",
        ],
    ),
    SettingDef(
        key="tool_expand",
        title="Tool Call Expansion",
        help="When to auto-expand tool call output blocks",
        type="choices",
        default="on-fail",
        choices=["always", "never", "on-fail", "on-success"],
    ),
    SettingDef(
        key="diff_view",
        title="Diff View Mode",
        help="How to display file diffs in tool calls",
        type="choices",
        default="auto",
        choices=["unified", "split", "auto"],
    ),
    SettingDef(
        key="sidebar_visible",
        title="Sidebar Visible",
        help="Show sidebar on startup",
        type="boolean",
        default=True,
    ),
    SettingDef(
        key="shell_command",
        title="Shell Command",
        help="Shell to use for the integrated terminal",
        type="string",
        default="",
    ),
    SettingDef(
        key="agent_url",
        title="Agent Server URL",
        help="URL of the agent server to connect to",
        type="string",
        default="http://localhost:8000",
    ),
    SettingDef(
        key="default_mode",
        title="Default Mode",
        help="Default interaction mode on startup",
        type="choices",
        default="ask",
        choices=["ask", "plan", "code", "chat", "build"],
    ),
    SettingDef(
        key="show_tokens",
        title="Show Token Usage",
        help="Display token count and cost in status bar",
        type="boolean",
        default=True,
    ),
    SettingDef(
        key="auto_scroll",
        title="Auto Scroll",
        help="Automatically scroll to bottom on new messages",
        type="boolean",
        default=True,
    ),
    SettingDef(
        key="approval_policy",
        title="Approval Policy",
        help="Tool execution approval policy",
        type="choices",
        default="on-request",
        choices=["on-request", "auto", "never"],
    ),
    SettingDef(
        key="sandbox_mode",
        title="Sandbox Mode",
        help="Workspace file operation boundary",
        type="choices",
        default="workspace-write",
        choices=["read-only", "workspace-write", "danger-full-access"],
    ),
    SettingDef(
        key="auto_allow",
        title="Auto-Allow Prefixes",
        help="Comma-separated command prefixes to auto-approve",
        type="string",
        default="",
    ),
    SettingDef(
        key="auto_compact",
        title="Auto Compact",
        help="Enable automatic context compaction",
        type="boolean",
        default=False,
    ),
    SettingDef(
        key="reasoning_effort",
        title="Reasoning Effort",
        help="Default reasoning effort tier",
        type="choices",
        default="high",
        choices=["off", "high", "max"],
    ),
    SettingDef(
        key="auto_model_routing",
        title="Auto Model Routing",
        help="Automatically select model and reasoning per turn",
        type="boolean",
        default=False,
    ),
    SettingDef(
        key="notification_method",
        title="Notification Method",
        help="Desktop notification method for long turns",
        type="choices",
        default="auto",
        choices=["auto", "osc9", "bel", "off"],
    ),
    SettingDef(
        key="notification_threshold_secs",
        title="Notification Threshold",
        help="Minimum turn duration (seconds) to trigger notification",
        type="integer",
        default=30,
    ),
    SettingDef(
        key="snapshots_enabled",
        title="Workspace Snapshots",
        help="Enable pre/post-turn workspace snapshots for rollback",
        type="boolean",
        default=True,
    ),
    SettingDef(
        key="snapshots_max_age_days",
        title="Snapshot Max Age",
        help="Maximum age in days before snapshots are pruned",
        type="integer",
        default=7,
    ),
    SettingDef(
        key="hooks_enabled",
        title="Hooks Enabled",
        help="Enable lifecycle hooks",
        type="boolean",
        default=True,
    ),
    SettingDef(
        key="trust_mode",
        title="Trust Mode",
        help="Bypass approval for non-destructive operations",
        type="boolean",
        default=False,
    ),
    SettingDef(
        key="max_concurrent_tasks",
        title="Max Concurrent Tasks",
        help="Maximum background tasks running simultaneously",
        type="integer",
        default=5,
    ),
]


class AppSettings:
    """TOML-backed application settings.

    Loads settings from a TOML file, applies defaults from the schema,
    and auto-saves changes. Provides dict-like access.
    """

    def __init__(self, settings_file: Path | None = None) -> None:
        """Initialize settings.

        Args:
            settings_file: Path to the settings TOML file.
        """
        self._file = settings_file or DEFAULT_SETTINGS_FILE
        self._data: dict[str, Any] = {}
        self._schema = {s.key: s for s in SETTINGS_SCHEMA}
        self._load()

    def _load(self) -> None:
        """Load settings from file, applying defaults."""
        # Apply defaults first
        for setting in SETTINGS_SCHEMA:
            self._data[setting.key] = setting.default

        # Override with file values
        if self._file.exists():
            try:
                import tomllib

                with open(self._file, "rb") as f:
                    file_data = tomllib.load(f)
                self._data.update(file_data)
            except Exception as e:
                logger.warning(f"Failed to load settings from {self._file}: {e}")

    def _save(self) -> None:
        """Save current settings to file."""
        try:
            self._file.parent.mkdir(parents=True, exist_ok=True)

            # Simple TOML serializer (avoids tomli_w dependency)
            lines = ["# Agent Terminal UI Settings\n"]
            for key, value in self._data.items():
                if isinstance(value, bool):
                    lines.append(f"{key} = {'true' if value else 'false'}\n")
                elif isinstance(value, int):
                    lines.append(f"{key} = {value}\n")
                elif isinstance(value, str):
                    lines.append(f'{key} = "{value}"\n')

            self._file.write_text("".join(lines))
        except Exception as e:
            logger.warning(f"Failed to save settings to {self._file}: {e}")

    def get(self, key: str, default: Any = None, expand: bool = True) -> Any:
        """Get a setting value.

        Args:
            key: The setting key.
            default: Default if key not found.
            expand: Whether to expand environment variables in string values.

        Returns:
            The setting value.
        """
        value = self._data.get(key, default)
        if expand and isinstance(value, str):
            value = os.path.expandvars(value)
        return value

    def set(self, key: str, value: Any) -> None:
        """Set a setting value and auto-save.

        Args:
            key: The setting key.
            value: The new value.
        """
        self._data[key] = value
        self._save()

    def __getitem__(self, key: str) -> Any:
        """Dict-like access."""
        return self._data[key]

    def __contains__(self, key: str) -> bool:
        """Dict-like contains check."""
        return key in self._data

    @property
    def schema(self) -> dict[str, SettingDef]:
        """The settings schema map."""
        return self._schema
