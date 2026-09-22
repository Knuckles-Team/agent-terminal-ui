# Interfaces

Agent Terminal UI keeps platform communication behind its `AgentClient` adapter.

| Interface | Role |
| --- | --- |
| Graph OS REST | `AGENT_URL` points to the gateway used for capability discovery and invocation, run inspection, and dashboard data. |
| ACP-style chat | `ACP_URL` points to the HTTP/SSE endpoint used for chat turns. The client uses this repository's JSON-RPC and SSE convention. |
| Interactive terminal | Textual renders sessions, tool activity, approvals, and workflow state. |
| Headless runner | Executes a session without importing the interactive Textual widget tree. |

The current Graph OS deployment does not mount this repository's ACP-style chat endpoint. A compatible service must be configured at `ACP_URL`; see the [configuration guide](configuration.md).
