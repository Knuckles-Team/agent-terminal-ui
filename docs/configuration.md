# Configuration

`tuig --help` lists the supported environment settings.

| Variable | Meaning |
| --- | --- |
| `AGENT_URL` | Arbora endpoint; default `http://localhost:8000`. |
| `AGENT_BEARER_TOKEN` | Caller credential for remote service access. |
| `AGENT_AUTH_MODE` | `bearer` by default; `none` only for explicit loopback. |
| `AGENT_TASK_ID` | Read an existing task, not a resumed conversation. |
| `AGENT_SUBMISSION_TIMEOUT_SECONDS` | 1..900 seconds; default 300. |
| `AGENT_INCLUDE_COMMITTED_EVENT` | `true` or `false` for committed-event reads. |
| `AGENT_THEME` | Native terminal theme. |
| `NO_COLOR` | Nonempty disables theme colors. |

Legacy Python settings, SQLite stores and hooks are not consumed by `tuig`.

## Explicit local backend (experimental)

```sh
tuig --local-runtime --local-model PROVIDER:MODEL
tuig --local-runtime --local-model PROVIDER:MODEL --headless --prompt "Hello"
```

This path starts the separately installed internal `arbora-acp` executable at
an absolute workspace root. It first checks beside the resolved `tuig` binary,
including when a symlink starts `tuig`. Only an absent sibling
permits lookup on `PATH`. An invalid sibling fails closed, without a second
lookup. Install directories and `PATH` must contain trusted executables. It does not start another frontend. Provider
credentials stay in the child environment; the central `AGENT_BEARER_TOKEN`
is not forwarded. Central Arbora remains the default, with no automatic fallback.

Local mode requires a POSIX host. Interactive sessions accept sequential text
turns of at most 16 KiB. Enter submits, `p` opens the next draft after an
acknowledged response, and `c` requests cancellation. The optional `--prompt`
submits the first turn. Headless mode still requires one prompt and then exits.
The encoded request must also fit the backend's 64 KiB frame limit.

The backend owns completed-text history. The UI keeps at most 128 KiB of displayed
text and labels clipping; this never changes backend history. Each process sends
at most 64 prompts. An unknown outcome closes the session without replay.
Only acknowledged completion or cancellation permits the next turn.

The client grants no file, terminal or permission capabilities. Ctrl+C quits,
requests cancellation if needed, then closes or stops and reaps the owned child.
Bounded queues keep cancellation independent of display backpressure. Both
paths use nonblocking terminal output. Unwritable interactive output closes
the session and reaps the backend instead of blocking cancellation. Initialization allows 30 seconds; each response
allows 330 seconds. Local mode cannot observe a central task or resume after
restart. Installed-candidate tests do not qualify a released dependency stack.

## Explicit context continuation

Use `tuig --continue CONTEXT_ID --prompt TEXT` (optionally `--headless`) to
submit a new turn to a known durable context. The identifier must be
`a2a-context-` followed by 64 lowercase hexadecimal digits. Observation,
`AGENT_TASK_ID`, duplicate flags and local ACP cannot be combined with this mode.

The server must advertise and activate the versioned completed-text-history
extension. Without that capability, Tuig submits nothing. A missing activation
response or changed returned context leaves the submission outcome unknown.
Tuig never retries it or starts a fresh context as a fallback. This check cannot
undo effects if discovery and submission reach different server versions.

Each invocation sends only the new prompt and generates a new message and
idempotency identifier. History remains upstream. This entry point does not
provide a history picker, prior-turn display or qualified restart recovery.
