#!/usr/bin/python
"""CSS styles for the Agent Terminal UI.

This module contains the global stylesheet for the Textual-based
terminal application, defining the visual appearance of the event log,
input area, status line, and activity timer.
"""

AGENT_APP_CSS: str = """
RichLog {
    height: 1fr;
    background: transparent;
    border: none;
    padding: 1 2 1 2;
    scrollbar-background: transparent;
    overflow-x: hidden;
}

InputTextArea {
    margin: 0 2 0 2;
    height: auto;
    max-height: 10;
    background: transparent;
    border-top: solid grey;
    border-bottom: solid grey;
    border-left: none;
    border-right: none;
    &>.text-area--cursor-line {
        background: transparent;
    }
}

StatusLine {
    dock: bottom;
    height: 1;
    margin: 0 2 1 2;
    padding: 0 6 0 2;
    background: transparent;
}

#status-mode {
    width: auto;
}

#status-model {
    width: 1fr;
    text-align: right;
    padding-right: 2;
    color: #6c6c6c;
}

#status-tokens {
    width: auto;
    color: #6c6c6c;
}

AgentTimer {
    height: auto;
    margin: 0 2 0 2;
    padding: 0 0 0 0;
    background: transparent;
}
"""
