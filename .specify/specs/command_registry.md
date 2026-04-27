# Command Registry Specification

## Overview
The command registry manages all slash commands and keyboard shortcuts in the TUI, providing an extensible system for user interaction and feature discovery.

## User Stories
- **As a User**, I want to use slash commands (e.g., `/help`, `/clear`) to perform common actions quickly.
- **As a Developer**, I want to easily register new commands without modifying the core app logic.
- **As a User**, I want to use keyboard shortcuts (e.g., `Ctrl+L`) to clear the log instantly.

## Functional Requirements
- **FR-001 (Command Registration)**: MUST use a registry pattern in `commands.py` for all slash commands.
- **FR-002 (Shortcut Binding)**: MUST bind keyboard shortcuts in `app.py` following Claude Code parity.
- **FR-003 (Help System)**: MUST provide an auto-generated `/help` output based on the registry.
- **FR-004 (Input Suggestion)**: MUST display a suggestion overlay when typing `/` in the input area.

## Success Criteria
- **Parity**: Matches all documented Claude Code shortcuts.
- **Extensibility**: Adding a new command requires only a single method and registry entry.
- **Consistency**: All commands follow a uniform output style.

## Data Model (Draft)
- `Command` (Entity)
- `Shortcut` (Entity)
- `InputSuggestion` (Entity)
