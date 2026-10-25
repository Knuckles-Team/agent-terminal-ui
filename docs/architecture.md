# Architecture

`tuig` is the sole Rust/Ratatui frontend. Tokio owns asynchronous requests;
Ratatui renders presentation state. Interactive and headless commands share
`ArboraClient`, task correlation, authentication and response validation.

```text
tuig -> Arbora A2A task submission and observation
     -> Arbora generated operations for run inspection and logs
Arbora -> agent runtime, authorization and durable state
```

The current implementation uses A2A and served HTTP operations, not a remote
Agent Client Protocol endpoint. A future ACP connection requires a producer
contract and qualification; it is not enabled by renaming the CLI.

The terminal does not own agent decisions, model execution or tool effects.
Unknown submission outcomes are not automatically replayed. Headless execution
never approves or cancels tasks. Interactive remote cancellation requires an
explicit confirmation. Existing credentials and authorization remain enforced.

The Python/Textual runtime has been removed. Native interactive composition,
streaming, approval attachment and durable resume remain open requirements,
not features supplied by a second frontend.
