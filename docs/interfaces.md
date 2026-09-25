# Interfaces

Agent Terminal UI keeps platform communication behind its `AgentClient` adapter.

| Interface | Role |
| --- | --- |
| Graph OS REST | `AGENT_URL` points to the gateway used for capability discovery and invocation, run inspection, and dashboard data. |
| A2A chat | `{AGENT_URL}/a2a` is Graph OS's authenticated JSON-RPC and SSE boundary for chat turns (`message/stream`, `tasks/resubscribe`, `tasks/cancel`). |
| Interactive terminal | Textual renders sessions, tool activity, approvals, and workflow state. |
| Headless runner | Executes a session without importing the interactive Textual widget tree. |

`AGENT_BEARER_TOKEN` authenticates both the REST gateway and A2A chat; see the [configuration guide](configuration.md).
