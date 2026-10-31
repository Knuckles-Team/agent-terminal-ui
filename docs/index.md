# Tuig

Tuig is the Rust/Ratatui terminal frontend for Arbora. The PyPI distribution
and the command are both `tuig`. There is no Python/Textual frontend.

Tuig reaches the ecosystem only through Arbora. Prompt submission and task
observation use Arbora A2A. Run inspection and logs use served Arbora operations.
Set `AGENT_URL` and `AGENT_BEARER_TOKEN` to connect.

Interactive and headless modes share one client. Headless mode never approves
or cancels a task.

See [start](start.md), [architecture](architecture.md), [configuration](configuration.md)
and [current status](status.md).
