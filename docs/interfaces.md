# Interfaces

Agent Terminal UI keeps platform communication behind its `AgentClient` adapter.

| Interface | Role |
| --- | --- |
| Graph OS REST | `AGENT_URL` points to the gateway used for capability discovery and invocation, run inspection, and dashboard data. |
| Graph OS A2A chat | `{AGENT_URL}/a2a` serves chat turns: `message/stream` (SSE), `tasks/resubscribe` and `tasks/cancel`, authenticated by `AGENT_BEARER_TOKEN`. |
| Interactive terminal | Textual renders sessions, tool activity, approvals, and workflow state. |
| Headless runner | Executes a session without importing the interactive Textual widget tree. |

See the [configuration guide](configuration.md) for the settings.
