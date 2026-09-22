# Status

Agent Terminal UI uses Graph OS REST APIs for capability discovery and invocation, run inspection, and dashboard data. Those integration paths are separate from chat.

Chat turns use Graph OS's authenticated A2A boundary: `message/stream` streams one durable task's state over SSE, `tasks/resubscribe` re-attaches and `tasks/cancel` cancels. Streamed events carry task state and, on completion, the agent's answer; there are no token deltas or tool-approval prompts.

See [Interfaces](interfaces.md) for the connection contract and [Architecture](architecture.md) for the request flow.
