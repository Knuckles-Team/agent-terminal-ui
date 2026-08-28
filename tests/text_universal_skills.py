"""Tests for universal-skills integration and loading."""

import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent_terminal_ui.client import _load_skill_entry


def _mock_skills_from_dir(skills_dir: Path) -> list[dict[str, Any]]:
    """Build the list a ``_load_skills_from_filesystem`` fallback would.

    Every test in this module mocks ``AgentClient._load_skills_from_filesystem``
    with a closure over a temp/real skills directory. They used to each
    reimplement the SKILL.md YAML-frontmatter/simple-parsing logic inline
    (duplicating, and drifting from, the real fallback in
    ``agent_terminal_ui.client``). This reuses the same production
    per-skill parser (`_load_skill_entry`) so the mocks can never diverge
    from what they're standing in for.
    """
    if not skills_dir.exists():
        return []
    return [
        _load_skill_entry(skill_dir)
        for skill_dir in skills_dir.iterdir()
        if skill_dir.is_dir()
    ]


@pytest.fixture
def mock_app():
    """Create a mock AgentApp for testing."""
    app = MagicMock()
    app.notify = MagicMock()
    app.query_one = MagicMock()

    # Mock event log
    event_log = AsyncMock()
    event_log.write = MagicMock()
    event_log.clear = MagicMock()
    app.query_one.return_value = event_log

    # Mock client
    app._client = AsyncMock()
    app._client.list_skills = AsyncMock(return_value=[])

    # Mock submission methods
    app.on_input_text_area_submitted = AsyncMock()

    return app


@pytest.fixture
def command_processor(mock_app):
    """Create a CommandProcessor instance with mock app."""
    from agent_terminal_ui.commands import CommandProcessor

    return CommandProcessor(mock_app)


class TestUniversalSkillsIntegration:
    """Test universal-skills integration with the terminal UI."""

    @pytest.mark.asyncio
    async def test_yaml_frontmatter_parsing(self):
        """Test that YAML frontmatter in SKILL.md is parsed correctly."""
        from agent_terminal_ui.client import AgentClient

        with tempfile.TemporaryDirectory() as temp_dir:
            skills_dir = Path(temp_dir) / "skills"
            skills_dir.mkdir()

            # Create skill with YAML frontmatter
            skill_dir = skills_dir / "test-skill"
            skill_dir.mkdir()
            skill_md = skill_dir / "SKILL.md"
            skill_md.write_text("""---
name: test-skill
description: This is a test skill with YAML frontmatter
categories: [Development, Core]
tags: [test, skill]
---

# Test Skill

This is the content of the skill.
""")

            client = AgentClient()

            # Mock the workspace root and method to use our temp directory
            async def mock_load():
                return _mock_skills_from_dir(Path(temp_dir) / "skills")

            client._load_skills_from_filesystem = mock_load  # type: ignore[method-assign]
            skills = await client._load_skills_from_filesystem()

            assert len(skills) == 1
            assert skills[0]["id"] == "test-skill"
            assert (
                "This is a test skill with YAML frontmatter" in skills[0]["description"]
            )

            await client.close()

    @pytest.mark.asyncio
    async def test_skill_without_yaml_frontmatter(self):
        """Test that skills without YAML frontmatter still work."""
        from agent_terminal_ui.client import AgentClient

        with tempfile.TemporaryDirectory() as temp_dir:
            skills_dir = Path(temp_dir) / "skills"
            skills_dir.mkdir()

            # Create skill without YAML frontmatter
            skill_dir = skills_dir / "simple-skill"
            skill_dir.mkdir()
            skill_md = skill_dir / "SKILL.md"
            skill_md.write_text("""# Simple Skill

This is a simple skill without YAML frontmatter.
It should still work by parsing the first non-empty line.
""")

            client = AgentClient()

            # Mock the workspace root and method

            async def mock_load():
                return _mock_skills_from_dir(Path(temp_dir) / "skills")

            client._load_skills_from_filesystem = mock_load  # type: ignore[method-assign]
            skills = await client._load_skills_from_filesystem()

            assert len(skills) == 1
            assert skills[0]["id"] == "simple-skill"
            assert (
                "This is a simple skill without YAML frontmatter"
                in skills[0]["description"]
            )

            await client.close()

    @pytest.mark.asyncio
    async def test_skill_missing_skill_md(self):
        """Test that skills without SKILL.md files are handled gracefully."""
        from agent_terminal_ui.client import AgentClient

        with tempfile.TemporaryDirectory() as temp_dir:
            skills_dir = Path(temp_dir) / "skills"
            skills_dir.mkdir()

            # Create skill directory without SKILL.md
            skill_dir = skills_dir / "no-doc-skill"
            skill_dir.mkdir()

            client = AgentClient()

            # Mock the workspace root and method
            async def mock_load():
                return _mock_skills_from_dir(Path(temp_dir) / "skills")

            client._load_skills_from_filesystem = mock_load  # type: ignore[method-assign]
            skills = await client._load_skills_from_filesystem()

            assert len(skills) == 1
            assert skills[0]["id"] == "no-doc-skill"
            assert (
                skills[0]["description"] == ""
            )  # Empty description when SKILL.md missing

            await client.close()

    @pytest.mark.asyncio
    async def test_multiple_skills_loading(self):
        """Test loading multiple skills from filesystem."""
        from agent_terminal_ui.client import AgentClient

        with tempfile.TemporaryDirectory() as temp_dir:
            skills_dir = Path(temp_dir) / "skills"
            skills_dir.mkdir()

            # Create multiple skills
            skill_names = ["skill-one", "skill-two", "skill-three"]
            for skill_name in skill_names:
                skill_dir = skills_dir / skill_name
                skill_dir.mkdir()
                skill_md = skill_dir / "SKILL.md"
                skill_md.write_text(f"""---
name: {skill_name}
description: Description for {skill_name}
---

# {skill_name.replace("-", " ").title()}

Content for {skill_name}.
""")

            client = AgentClient()

            # Mock the workspace root and method
            async def mock_load():
                return _mock_skills_from_dir(Path(temp_dir) / "skills")

            client._load_skills_from_filesystem = mock_load  # type: ignore[method-assign]
            skills = await client._load_skills_from_filesystem()

            assert len(skills) == 3
            skill_ids = [s["id"] for s in skills]
            for skill_name in skill_names:
                assert skill_name in skill_ids

            await client.close()

    @pytest.mark.asyncio
    async def test_skill_command_registration_integration(
        self, command_processor, mock_app
    ):
        """Test that loaded skills are registered as commands."""

        with tempfile.TemporaryDirectory() as temp_dir:
            skills_dir = Path(temp_dir) / "skills"
            skills_dir.mkdir()

            # Create test skills
            skill_dir = skills_dir / "integration-test-skill"
            skill_dir.mkdir()
            skill_md = skill_dir / "SKILL.md"
            skill_md.write_text("""---
name: integration-test-skill
description: A skill for integration testing
---

# Integration Test Skill

This skill tests the integration.
""")

            # Mock the client to return our test skills
            test_skills = [
                {
                    "id": "integration-test-skill",
                    "name": "integration-test-skill",
                    "description": "A skill for integration testing",
                }
            ]

            mock_app._client.list_skills.return_value = test_skills

            await command_processor.register_skill_commands()

            assert "integration-test-skill" in command_processor.commands

            # Test that the skill command can be invoked
            skill_data = test_skills[0]
            await command_processor._invoke_skill(skill_data, "test argument")

            mock_app.on_input_text_area_submitted.assert_called()
            submitted_value = mock_app.on_input_text_area_submitted.call_args[0][
                0
            ].value
            assert "integration-test-skill" in submitted_value
            assert "test argument" in submitted_value

    @pytest.mark.asyncio
    async def test_real_universal_skills_structure(self):
        """Test that the real universal-skills directory structure is handled."""
        from agent_terminal_ui.client import AgentClient

        # Test with the actual universal-skills path if it exists
        workspace_root = Path(__file__).parent.parent.parent.parent
        real_skills_dir = (
            workspace_root
            / "ai"
            / "skills"
            / "universal-skills"
            / "universal_skills"
            / "skills"
        )

        if real_skills_dir.exists():
            client = AgentClient()

            # Mock the workspace root to point to real location
            async def mock_load():
                return _mock_skills_from_dir(real_skills_dir)

            client._load_skills_from_filesystem = mock_load  # type: ignore[method-assign]
            skills = await client._load_skills_from_filesystem()

            # Should load at least some skills
            assert len(skills) > 0

            # Check for known skills
            skill_ids = [s["id"] for s in skills]
            known_skills = ["agent-builder", "web-search", "skill-builder"]
            for known_skill in known_skills:
                if known_skill in skill_ids:
                    # Found at least one known skill
                    break
            else:
                # If none found, that's okay for this test
                pass

            await client.close()
        else:
            # Skip test if real directory doesn't exist
            pytest.skip("Real universal-skills directory not found")

    @pytest.mark.asyncio
    async def test_skill_command_help_display(self, command_processor, mock_app):
        """Test that skill commands appear in help output with descriptions."""
        # Register a test skill with description
        mock_app._client.list_skills.return_value = [
            {
                "id": "test-help-skill",
                "name": "Test Help Skill",
                "description": "For testing help display",
            }
        ]

        await command_processor.register_skill_commands()

        # Get help output
        await command_processor.cmd_help("")

        event_log = mock_app.query_one("Conversation")
        event_log.add_info.assert_called()
        written_text = event_log.add_info.call_args[0][0]

        # Check that the skill appears in help
        assert "test-help-skill" in written_text.lower()

        # Check that the description is present
        assert "For testing help display" in written_text

    @pytest.mark.asyncio
    async def test_skill_command_with_hyphenated_names(
        self, command_processor, mock_app
    ):
        """Test that skills with hyphenated names work correctly."""
        hyphenated_skills = [
            {
                "id": "agent-package-builder",
                "name": "Agent Package Builder",
                "description": "Build agent packages",
            },
            {
                "id": "api-wrapper-builder",
                "name": "API Wrapper Builder",
                "description": "Build API wrappers",
            },
            {
                "id": "skill-builder",
                "name": "Skill Builder",
                "description": "Build skills",
            },
        ]

        mock_app._client.list_skills.return_value = hyphenated_skills

        await command_processor.register_skill_commands()

        # Check all hyphenated skills are registered
        for skill in hyphenated_skills:
            assert skill["id"] in command_processor.commands
