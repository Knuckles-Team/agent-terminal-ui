"""Tests for slash commands in the terminal UI."""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def mock_app():
    """Create a mock AgentApp for testing."""
    app = MagicMock()

    # Mock essential app methods
    app.notify = MagicMock()
    app.query_one = MagicMock()

    # Mock event log
    event_log = MagicMock()
    event_log.write = MagicMock()
    event_log.clear = MagicMock()
    app.query_one.return_value = event_log

    # Mock client
    app._client = AsyncMock()
    app._client.get_mcp_config = AsyncMock(return_value={})
    app._client.list_mcp_tools = AsyncMock(return_value=[])
    app._client.list_chats = AsyncMock(return_value=[])
    app._client.list_skills = AsyncMock(return_value=[])

    # Mock screen methods
    app.push_screen = MagicMock()

    # Mock submission methods
    app.on_input_text_area_submitted = AsyncMock()

    # Mock status line
    status_line = MagicMock()
    status_line.set_mode = MagicMock()
    app.query_one.side_effect = lambda selector: (
        status_line if "StatusLine" in str(selector) else event_log
    )

    # Mock mode attribute
    app._agent_mode = "ask"

    return app


@pytest.fixture
def command_processor(mock_app):
    """Create a CommandProcessor instance with mock app."""
    from agent_terminal_ui.commands import CommandProcessor

    return CommandProcessor(mock_app)


class TestCommandProcessor:
    """Test the CommandProcessor class."""

    def test_init(self, mock_app):
        """Test CommandProcessor initialization."""
        from agent_terminal_ui.commands import CommandProcessor

        processor = CommandProcessor(mock_app)

        assert processor.app == mock_app
        assert "help" in processor.commands
        assert "clear" in processor.commands
        assert "exit" in processor.commands
        assert "theme" in processor.commands

    @pytest.mark.asyncio
    async def test_process_non_command(self, command_processor):
        """Test that non-command text returns False."""
        result = await command_processor.process("hello world")
        assert result is False

    @pytest.mark.asyncio
    async def test_process_plain_exit(self, command_processor, mock_app):
        """Test that plain 'exit' without slash shows exit confirmation dialog."""
        await command_processor.process("exit")
        # Should push exit confirmation screen
        mock_app.push_screen.assert_called_once()

        # Verify the screen pushed is ExitConfirmScreen
        call_args = mock_app.push_screen.call_args
        from agent_terminal_ui.tui.exit_confirm_screen import ExitConfirmScreen

        assert isinstance(call_args[0][0], ExitConfirmScreen)

    @pytest.mark.asyncio
    async def test_process_plain_quit(self, command_processor, mock_app):
        """Test that plain 'quit' without slash shows exit confirmation dialog."""
        await command_processor.process("quit")
        # Should push exit confirmation screen
        mock_app.push_screen.assert_called_once()

        # Verify the screen pushed is ExitConfirmScreen
        call_args = mock_app.push_screen.call_args
        from agent_terminal_ui.tui.exit_confirm_screen import ExitConfirmScreen

        assert isinstance(call_args[0][0], ExitConfirmScreen)

    @pytest.mark.asyncio
    async def test_process_plain_exit_with_spaces(self, command_processor, mock_app):
        """Test that plain 'exit' with spaces shows exit confirmation dialog."""
        await command_processor.process("  exit  ")
        # Should push exit confirmation screen
        mock_app.push_screen.assert_called_once()

        # Verify the screen pushed is ExitConfirmScreen
        call_args = mock_app.push_screen.call_args
        from agent_terminal_ui.tui.exit_confirm_screen import ExitConfirmScreen

        assert isinstance(call_args[0][0], ExitConfirmScreen)

    @pytest.mark.asyncio
    async def test_process_slash_command(self, command_processor):
        """Test processing a slash command."""
        result = await command_processor.process("/help")
        assert result is True

    @pytest.mark.asyncio
    async def test_process_unknown_command(self, command_processor, mock_app):
        """Test processing an unknown slash command."""
        result = await command_processor.process("/unknown")
        assert result is True
        mock_app.notify.assert_called()
        assert "Unknown command" in mock_app.notify.call_args[0][0]

    @pytest.mark.asyncio
    async def test_process_command_with_args(self, command_processor):
        """Test processing a command with arguments."""
        result = await command_processor.process("/model gpt-4")
        assert result is True


class TestHelpCommand:
    """Test the /help command."""

    @pytest.mark.asyncio
    async def test_cmd_help(self, command_processor, mock_app):
        """Test the help command displays available commands."""
        await command_processor.cmd_help("")

        event_log = mock_app.query_one("#event-log")
        event_log.write.assert_called()
        written_text = event_log.write.call_args[0][0]
        assert "Available Commands" in written_text
        assert "/help" in written_text
        assert "/clear" in written_text
        assert "/exit" in written_text


class TestClearCommand:
    """Test the /clear command."""

    @pytest.mark.asyncio
    async def test_cmd_clear(self, command_processor, mock_app):
        """Test the clear command clears the event log."""
        await command_processor.cmd_clear("")

        event_log = mock_app.query_one("#event-log")
        event_log.clear.assert_called_once()


class TestExitCommand:
    """Test the /exit command and exit confirmation overlay."""

    @pytest.mark.asyncio
    async def test_cmd_exit(self, command_processor, mock_app):
        """Test the exit command shows exit confirmation dialog."""
        await command_processor.cmd_exit("")

        # Should push exit confirmation screen
        mock_app.push_screen.assert_called_once()

        # Verify the screen pushed is ExitConfirmScreen
        call_args = mock_app.push_screen.call_args
        from agent_terminal_ui.tui.exit_confirm_screen import ExitConfirmScreen

        assert isinstance(call_args[0][0], ExitConfirmScreen)


class TestMCPCommand:
    """Test the /mcp command."""

    @pytest.mark.asyncio
    async def test_cmd_mcp(self, command_processor, mock_app):
        """Test the mcp command opens MCP screen."""
        await command_processor.cmd_mcp("")

        mock_app._client.get_mcp_config.assert_called_once()
        mock_app._client.list_mcp_tools.assert_called_once()
        mock_app.push_screen.assert_called_once()


class TestHistoryCommand:
    """Test the /history command."""

    @pytest.mark.asyncio
    async def test_cmd_history(self, command_processor, mock_app):
        """Test the history command opens history screen."""
        await command_processor.cmd_history("")

        mock_app._client.list_chats.assert_called_once()
        mock_app.push_screen.assert_called_once()


class TestImageCommand:
    """Test the /image command."""

    @pytest.mark.asyncio
    async def test_cmd_image_success(self, command_processor, mock_app):
        """Test successful image attachment."""
        # Create a temporary test image file
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            temp_path = f.name
            f.write(b"fake image data")

        try:
            await command_processor.cmd_image(temp_path)

            mock_app.notify.assert_called()
            assert "Attached image" in mock_app.notify.call_args[0][0]
            assert hasattr(mock_app, "_pending_parts")
        finally:
            Path(temp_path).unlink()

    @pytest.mark.asyncio
    async def test_cmd_image_not_found(self, command_processor, mock_app):
        """Test image command with non-existent file."""
        await command_processor.cmd_image("/nonexistent/image.png")

        mock_app.notify.assert_called()
        assert "not found" in mock_app.notify.call_args[0][0]
        assert mock_app.notify.call_args[1]["severity"] == "error"

    @pytest.mark.asyncio
    async def test_cmd_image_jpeg(self, command_processor, mock_app):
        """Test image command with JPEG file."""
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            temp_path = f.name
            f.write(b"fake jpeg data")

        try:
            await command_processor.cmd_image(temp_path)

            mock_app.notify.assert_called()
            assert hasattr(mock_app, "_pending_parts")
        finally:
            Path(temp_path).unlink()

    @pytest.mark.asyncio
    async def test_cmd_image_with_quotes(self, command_processor, mock_app):
        """Test image command with quoted path."""
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            temp_path = f.name
            f.write(b"fake image data")

        try:
            await command_processor.cmd_image(f'"{temp_path}"')

            mock_app.notify.assert_called()
        finally:
            Path(temp_path).unlink()


class TestModeCommands:
    """Test mode switching commands (/plan, /chat, /build)."""

    @pytest.mark.asyncio
    async def test_cmd_plan(self, command_processor, mock_app):
        """Test the plan command switches to plan mode."""
        await command_processor.cmd_plan("")

        assert mock_app._agent_mode == "plan"
        status_line = mock_app.query_one("StatusLine")
        status_line.set_mode.assert_called_with("plan")

    @pytest.mark.asyncio
    async def test_cmd_plan_with_args(self, command_processor, mock_app):
        """Test the plan command with arguments submits prompt."""
        await command_processor.cmd_plan("create a plan")

        assert mock_app._agent_mode == "plan"
        mock_app.on_input_text_area_submitted.assert_called()

    @pytest.mark.asyncio
    async def test_cmd_chat(self, command_processor, mock_app):
        """Test the chat command switches to chat mode."""
        await command_processor.cmd_chat("")

        assert mock_app._agent_mode == "ask"
        status_line = mock_app.query_one("StatusLine")
        status_line.set_mode.assert_called_with("chat")

    @pytest.mark.asyncio
    async def test_cmd_build(self, command_processor, mock_app):
        """Test the build command switches to code mode."""
        await command_processor.cmd_build("")

        assert mock_app._agent_mode == "code"
        status_line = mock_app.query_one("StatusLine")
        status_line.set_mode.assert_called_with("code")


class TestWorkflowCommands:
    """Test workflow commands (/init, /review, /test, /search)."""

    @pytest.mark.asyncio
    async def test_cmd_init(self, command_processor, mock_app):
        """Test the init command submits SDD initialization prompt."""
        await command_processor.cmd_init("")

        mock_app.on_input_text_area_submitted.assert_called()
        submitted_value = mock_app.on_input_text_area_submitted.call_args[0][0].value
        assert "setup_sdd" in submitted_value

    @pytest.mark.asyncio
    async def test_cmd_review(self, command_processor, mock_app):
        """Test the review command submits code review prompt."""
        await command_processor.cmd_review("")

        mock_app.on_input_text_area_submitted.assert_called()
        submitted_value = mock_app.on_input_text_area_submitted.call_args[0][0].value
        assert "code review" in submitted_value

    @pytest.mark.asyncio
    async def test_cmd_review_with_args(self, command_processor, mock_app):
        """Test the review command with additional arguments."""
        await command_processor.cmd_review("focus on security")

        mock_app.on_input_text_area_submitted.assert_called()
        submitted_value = mock_app.on_input_text_area_submitted.call_args[0][0].value
        assert "security" in submitted_value

    @pytest.mark.asyncio
    async def test_cmd_test(self, command_processor, mock_app):
        """Test the test command submits test prompt."""
        await command_processor.cmd_test("")

        mock_app.on_input_text_area_submitted.assert_called()
        submitted_value = mock_app.on_input_text_area_submitted.call_args[0][0].value
        assert "Run tests" in submitted_value

    @pytest.mark.asyncio
    async def test_cmd_search_with_query(self, command_processor, mock_app):
        """Test the search command with a query."""
        await command_processor.cmd_search("authentication")

        mock_app.on_input_text_area_submitted.assert_called()
        submitted_value = mock_app.on_input_text_area_submitted.call_args[0][0].value
        assert "authentication" in submitted_value

    @pytest.mark.asyncio
    async def test_cmd_search_without_query(self, command_processor, mock_app):
        """Test the search command without a query shows usage."""
        await command_processor.cmd_search("")

        mock_app.notify.assert_called()
        assert "Usage" in mock_app.notify.call_args[0][0]
        mock_app.on_input_text_area_submitted.assert_not_called()


class TestStatsCommand:
    """Test the /stats command."""

    @pytest.mark.asyncio
    async def test_cmd_stats_with_usage(self, command_processor, mock_app):
        """Test stats command when usage data is available."""
        mock_app._last_usage = {"total_tokens": 1000, "estimated_cost_usd": 0.05}

        await command_processor.cmd_stats("")

        event_log = mock_app.query_one("#event-log")
        event_log.write.assert_called()
        written_text = event_log.write.call_args[0][0]
        assert "Session Statistics" in written_text
        assert "1000" in written_text
        assert "0.05" in written_text

    @pytest.mark.asyncio
    async def test_cmd_stats_without_usage(self, command_processor, mock_app):
        """Test stats command when usage data is not available."""
        # Ensure _last_usage is not set
        if hasattr(mock_app, "_last_usage"):
            delattr(mock_app, "_last_usage")

        await command_processor.cmd_stats("")

        event_log = mock_app.query_one("#event-log")
        event_log.write.assert_called()
        written_text = event_log.write.call_args[0][0]
        assert "not yet available" in written_text

    @pytest.mark.asyncio
    async def test_cmd_cost_alias(self, command_processor, mock_app):
        """Test that /cost is an alias for /stats."""
        # Both commands should map to the same handler
        assert command_processor.commands["cost"] == command_processor.commands["stats"]


class TestModelCommand:
    """Test the /model command."""

    @pytest.mark.asyncio
    async def test_cmd_model_without_args(self, command_processor, mock_app):
        """Test model command without args shows current model."""
        await command_processor.cmd_model("")

        event_log = mock_app.query_one("#event-log")
        event_log.write.assert_called()
        written_text = event_log.write.call_args[0][0]
        assert "Model Configuration" in written_text
        assert "Usage" in written_text

    @pytest.mark.asyncio
    async def test_cmd_model_with_args(self, command_processor, mock_app):
        """Test model command with args switches model."""
        await command_processor.cmd_model("gpt-4")

        assert mock_app._current_model == "gpt-4"
        mock_app.notify.assert_called()
        assert "Switched to model" in mock_app.notify.call_args[0][0]


class TestThemeCommand:
    """Test the /theme command."""

    @pytest.mark.asyncio
    async def test_cmd_theme_without_args(self, command_processor, mock_app):
        """Test theme command without args lists available themes."""
        await command_processor.cmd_theme("")

        event_log = mock_app.query_one("#event-log")
        event_log.write.assert_called()
        written_text = event_log.write.call_args[0][0]
        assert "Theme System" in written_text
        assert "Available themes" in written_text

    @pytest.mark.asyncio
    async def test_cmd_theme_with_args(self, command_processor, mock_app):
        """Test theme command with args switches theme."""
        mock_app.switch_theme = MagicMock()

        await command_processor.cmd_theme("dracula")

        mock_app.switch_theme.assert_called_with("dracula")


class TestSkillCommands:
    """Test dynamic skill command registration."""

    @pytest.mark.asyncio
    async def test_register_skill_commands(self, command_processor, mock_app):
        """Test registering skills as commands."""
        mock_app._client.list_skills.return_value = [
            {"id": "test-skill", "name": "Test Skill", "description": "A test skill"}
        ]

        await command_processor.register_skill_commands()

        assert "test-skill" in command_processor.commands
        event_log = mock_app.query_one("#event-log")
        event_log.write.assert_called()
        written_text = event_log.write.call_args[0][0]
        assert "1 skills" in written_text

    @pytest.mark.asyncio
    async def test_register_skill_commands_empty(self, command_processor, mock_app):
        """Test registering when no skills available."""
        mock_app._client.list_skills.return_value = []

        await command_processor.register_skill_commands()

        event_log = mock_app.query_one("#event-log")
        event_log.write.assert_called()
        written_text = event_log.write.call_args[0][0]
        assert "No skills" in written_text

    @pytest.mark.asyncio
    async def test_register_skill_commands_error(self, command_processor, mock_app):
        """Test error handling during skill registration."""
        mock_app._client.list_skills.side_effect = Exception("API error")

        await command_processor.register_skill_commands()

        event_log = mock_app.query_one("#event-log")
        event_log.write.assert_called()
        written_text = event_log.write.call_args[0][0]
        assert "Failed" in written_text

    @pytest.mark.asyncio
    async def test_invoke_skill_without_args(self, command_processor, mock_app):
        """Test invoking a skill without arguments."""
        skill = {"name": "test-skill", "description": "A test skill"}

        await command_processor._invoke_skill(skill, "")

        mock_app.on_input_text_area_submitted.assert_called()
        submitted_value = mock_app.on_input_text_area_submitted.call_args[0][0].value
        assert "test-skill" in submitted_value
        assert "A test skill" in submitted_value

    @pytest.mark.asyncio
    async def test_invoke_skill_with_args(self, command_processor, mock_app):
        """Test invoking a skill with arguments."""
        skill = {"name": "test-skill", "description": "A test skill"}

        await command_processor._invoke_skill(skill, "with arguments")

        mock_app.on_input_text_area_submitted.assert_called()
        submitted_value = mock_app.on_input_text_area_submitted.call_args[0][0].value
        assert "test-skill" in submitted_value
        assert "with arguments" in submitted_value


class TestSkillFileSystemLoading:
    """Test filesystem-based skill loading as fallback."""

    @pytest.mark.asyncio
    async def test_load_skills_from_filesystem(self, mock_app):
        """Test loading skills from filesystem when backend fails."""
        import tempfile
        from pathlib import Path

        from agent_terminal_ui.client import AgentClient

        # Create a temporary skills directory structure
        with tempfile.TemporaryDirectory() as temp_dir:
            skills_dir = Path(temp_dir) / "skills"
            skills_dir.mkdir()

            # Create a mock skill directory
            skill_dir = skills_dir / "test-skill"
            skill_dir.mkdir()

            # Create SKILL.md
            skill_md = skill_dir / "SKILL.md"
            skill_md.write_text(
                "# Test Skill\nThis is a test skill for testing purposes."
            )

            # Create another skill
            skill_dir2 = skills_dir / "another-skill"
            skill_dir2.mkdir()
            skill_md2 = skill_dir2 / "SKILL.md"
            skill_md2.write_text("# Another Skill\nAnother test skill.")

            # Mock the client to use our temp directory
            client = AgentClient()

            # Temporarily override the workspace root to point to our temp dir

            async def mock_load():
                # Manually set up the skills directory
                client_skills_dir = Path(temp_dir) / "skills"
                if client_skills_dir.exists():
                    skills = []
                    for skill_dir in client_skills_dir.iterdir():
                        if skill_dir.is_dir():
                            skill_id = skill_dir.name
                            skill_md = skill_dir / "SKILL.md"
                            description = ""
                            if skill_md.exists():
                                content = skill_md.read_text(encoding="utf-8")
                                for line in content.split("\n"):
                                    line = line.strip()
                                    if line and not line.startswith("#"):
                                        description = line
                                        break

                            skills.append(
                                {
                                    "id": skill_id,
                                    "name": skill_id,
                                    "description": description,
                                }
                            )

                    return skills
                return []

            client._load_skills_from_filesystem = mock_load  # type: ignore[method-assign]

            # Test the loading
            skills = await client._load_skills_from_filesystem()

            assert len(skills) == 2
            assert any(s["id"] == "test-skill" for s in skills)
            assert any(s["id"] == "another-skill" for s in skills)
            assert any("This is a test skill" in s["description"] for s in skills)

    @pytest.mark.asyncio
    async def test_load_skills_nonexistent_directory(self, mock_app):
        """Test loading skills when directory doesn't exist."""
        from agent_terminal_ui.client import AgentClient

        client = AgentClient()

        # Mock to return non-existent directory
        async def mock_load():
            return []

        client._load_skills_from_filesystem = mock_load  # type: ignore[method-assign]
        skills = await client._load_skills_from_filesystem()

        assert skills == []


class TestCommandErrorHandling:
    """Test error handling in command processing."""

    @pytest.mark.asyncio
    async def test_command_exception_handling(self, command_processor, mock_app):
        """Test that exceptions in commands are caught and reported."""

        # Make a command raise an exception
        async def failing_command(args):
            raise ValueError("Test error")

        command_processor.commands["fail"] = failing_command

        await command_processor.process("/fail")

        mock_app.notify.assert_called()
        assert "Error executing" in mock_app.notify.call_args[0][0]
        assert mock_app.notify.call_args[1]["severity"] == "error"


class TestQueueCommand:
    """Test the /queue command and queue functionality."""

    @pytest.mark.asyncio
    async def test_cmd_queue_empty(self, command_processor, mock_app):
        """Test /queue command when queue is empty."""
        mock_app._user_message_queue = []
        await command_processor.cmd_queue("")

        # Should write message about empty queue
        event_log = mock_app.query_one("#event-log")
        event_log.write.assert_called_once()

    @pytest.mark.asyncio
    async def test_cmd_queue_with_messages(self, command_processor, mock_app):
        """Test /queue command with queued messages."""
        mock_app._user_message_queue = [
            {"message": "Test message 1", "parts": [], "timestamp": 123456},
            {"message": "Test message 2", "parts": [], "timestamp": 123457},
        ]
        await command_processor.cmd_queue("")

        # Should write message showing queued messages
        event_log = mock_app.query_one("#event-log")
        event_log.write.assert_called_once()

    @pytest.mark.asyncio
    async def test_cmd_queue_clear(self, command_processor, mock_app):
        """Test /queue:clear command."""
        mock_app._user_message_queue = [
            {"message": "Test message 1", "parts": [], "timestamp": 123456},
            {"message": "Test message 2", "parts": [], "timestamp": 123457},
        ]
        await command_processor.cmd_queue_clear("")

        # Should clear the queue
        assert len(mock_app._user_message_queue) == 0

    @pytest.mark.asyncio
    async def test_cmd_queue_toggle(self, command_processor, mock_app):
        """Test /queue:toggle command."""
        initial_state = mock_app._queue_enabled
        await command_processor.cmd_queue_toggle("")

        # Should toggle the queue enabled state
        assert mock_app._queue_enabled != initial_state


class TestCommandEdgeCases:
    """Test edge cases in command processing."""

    @pytest.mark.asyncio
    async def test_empty_command(self, command_processor, mock_app):
        """Test processing an empty slash command shows unknown command."""
        result = await command_processor.process("/")

        assert result is True
        mock_app.notify.assert_called()
        assert "Unknown command" in mock_app.notify.call_args[0][0]

    @pytest.mark.asyncio
    async def test_command_case_insensitive(self, command_processor, mock_app):
        """Test that commands are case-insensitive."""
        await command_processor.process("/HELP")
        event_log = mock_app.query_one("#event-log")
        event_log.write.assert_called()

    @pytest.mark.asyncio
    async def test_command_with_extra_spaces(self, command_processor, mock_app):
        """Test command with extra spaces around args."""
        await command_processor.process("/model   gpt-4   ")
        assert mock_app._current_model == "gpt-4"

    @pytest.mark.asyncio
    async def test_plain_exit_case_insensitive(self, command_processor, mock_app):
        """Test that plain exit is case-insensitive."""
        await command_processor.process("EXIT")
        # Should push exit confirmation screen
        mock_app.push_screen.assert_called()

        # Verify the screen pushed is ExitConfirmScreen
        call_args = mock_app.push_screen.call_args
        from agent_terminal_ui.tui.exit_confirm_screen import ExitConfirmScreen

        assert isinstance(call_args[0][0], ExitConfirmScreen)

        await command_processor.process("QUIT")
        # Should push exit confirmation screen
        mock_app.push_screen.assert_called()

        # Verify the screen pushed is ExitConfirmScreen
        call_args = mock_app.push_screen.call_args
        assert isinstance(call_args[0][0], ExitConfirmScreen)
