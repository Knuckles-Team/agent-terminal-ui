# Start

Install a qualified native wheel with `pip install agent-terminal-ui`, then run
`tuig --help`. Older published releases may predate the native-only cutover.

Set `AGENT_URL` and `AGENT_BEARER_TOKEN` for an authorized Arbora service.
Remote access requires TLS. Anonymous access is restricted to explicit loopback
`AGENT_AUTH_MODE=none` without a bearer token.

Run `tuig --prompt "Your task"` or `tuig --headless --prompt "Your task"`.
`tuig --observe-task TASK_ID` reads an existing task without new submission.
