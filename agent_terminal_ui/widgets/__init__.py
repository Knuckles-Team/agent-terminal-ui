"""Widget modules for the Agent Terminal UI.

Provides the structured UI components used in the conversation interface:
- Conversation: main scrollable message container
- UserMessage: user input block
- AgentResponse: streaming Markdown response block
- ToolCallBlock: expandable tool call display
- Throbber: inline thinking indicator

Concept: AU-018 (TUI Widget Architecture)
"""

from agent_terminal_ui.widgets.agent_response import AgentResponse
from agent_terminal_ui.widgets.conversation import Conversation
from agent_terminal_ui.widgets.throbber import Throbber
from agent_terminal_ui.widgets.tool_call_block import ToolCallBlock
from agent_terminal_ui.widgets.user_message import UserMessage
from agent_terminal_ui.widgets.utils import (
    format_agent_prefix,
    format_agent_prefix_markup,
    get_agent_color,
)

__all__ = [
    "AgentResponse",
    "Conversation",
    "Throbber",
    "ToolCallBlock",
    "UserMessage",
    "format_agent_prefix",
    "format_agent_prefix_markup",
    "get_agent_color",
]
