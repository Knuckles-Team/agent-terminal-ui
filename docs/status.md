# Status

Agent Terminal UI uses Graph OS REST APIs for capability discovery and invocation, run inspection, and dashboard data. Those integration paths are separate from chat.

Chat turns use Graph OS's authenticated A2A boundary: `message/stream` streams one durable task's state over SSE, `tasks/resubscribe` re-attaches and `tasks/cancel` cancels. Streamed events carry task state, not token deltas or tool-approval prompts; an agent's answer text is not yet readable through the A2A task.

See [Interfaces](interfaces.md) for the connection contract and [Architecture](architecture.md) for the request flow.
