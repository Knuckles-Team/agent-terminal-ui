# Project Constitution - agent-terminal-ui

## Vision & Mission
**agent-terminal-ui** is a production-grade, Textual-based terminal interface designed to provide a fast, keyboard-centric workflow for agentic orchestration. It aims for feature parity with **Claude Code** while remaining protocol-native (AG-UI/ACP).

## Core Principles
### Guiding Principles
- **Production-Grade Python**: Follow best open-source practices. Shortcuts are prohibited.
- **Keyboard First**: Every action should be accessible via keyboard shortcuts or slash commands.
- **Type Safety**: Use `ty` for strict type checking. All code must have appropriate type hints.
- **Declarative UI**: Leverage Textual's reactive framework and CSS for layout and styling.

### Normative Statements
- **File Operations**: MUST use `pathlib` for all filesystem interactions.
- **Logging**: Use `loguru` for internal diagnostics (only when explicitly requested).
- **Style**: Follow the Google Python Style Guide.
- **Testing**: Use `pytest` and `pytest-asyncio` for all tests.

## Governance
- **Protocol Parity**: The TUI must support both AG-UI and ACP protocols.
- **Extensibility**: Tool formatters and slash commands must be implemented via registry patterns to allow easy expansion.
- **Decision Making**: Slash commands and shortcuts are prioritized based on user ergonomics and CLI standards.

## Quality Gates
- **Testing**:
  - All new features MUST be implemented with corresponding **Pytests**.
- **Verification Loop**:
  - After any code change, `pre-commit run --all-files` MUST be executed to verify integrity.
  - If issues are introduced, the implementation plan MUST be updated to address them, and the process repeated until all checks pass.
- **Type Check**: MUST pass `ty` type checking before merge.

## Tech Stack & Standards
- **Framework**: Textual (TUI framework).
- **Formatting**: Rich.
- **Networking**: httpx.
- **Type Checking**: ty (Astral).
- **Linting**: Ruff, Mypy.


## First Principles Architecture
- Four new foundational concepts (AU-024 through AU-027) that rewire the routing, dispatch, and feedback layers from first principles.

## Ecosystem Human Interface Guidelines (HIG)

All user-facing projects MUST strictly adhere to the unified **CONCEPT-HIG** (Human Interface Guidelines) to ensure ecosystem cohesion.

1. **Dynamic Brand Theming**: UIs MUST NOT use hard-coded branding colors. They MUST ingest a base brand color (e.g., OKLCH, Hex, or QPalette) and generate application palettes dynamically.
2. **Collapsible "Rail" Navigation**: All primary application navigation menus MUST support a graceful collapse into an icon-only "rail" to maximize workspace real-estate. Text labels must degrade to tooltips.
3. **Depth-Aware Modals**: Disruptive configurations or tool-approval flows (Tool Guards) MUST be presented in depth-separated modals. Where supported by the OS/Framework (Web, Qt), these MUST utilize glassmorphic/blur effects. In environments where it is not (Terminal), they MUST use simulated depth (borders, shadows, and z-index layers).
