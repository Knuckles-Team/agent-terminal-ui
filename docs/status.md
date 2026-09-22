# Status

Agent Terminal UI uses Graph OS REST APIs for capability discovery and invocation, run inspection, and dashboard data. Those integration paths are separate from chat.

The main chat client uses this repository's HTTP/SSE implementation of an ACP-style JSON-RPC transport. The current Graph OS deployment does not mount that chat endpoint, so chat requires a compatible ACP service configured through `ACP_URL`. The client does not use Zed's ACP SDK.

See [Interfaces](interfaces.md) for the connection contract and [Architecture](architecture.md) for the request flow.
