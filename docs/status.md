# Status

Agent Terminal UI uses Graph OS REST APIs for capability discovery and invocation, run inspection, and dashboard data. Those integration paths are separate from chat.

Chat turns use Graph OS's authenticated A2A JSON-RPC and SSE boundary at `{AGENT_URL}/a2a` (`message/stream`, `tasks/resubscribe`, `tasks/cancel`) with `AGENT_BEARER_TOKEN`.

See [Interfaces](interfaces.md) for the connection contract and [Architecture](architecture.md) for the request flow.
