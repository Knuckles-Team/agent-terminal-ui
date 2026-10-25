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
tuig --local-runtime --local-model PROVIDER:MODEL --headless --prompt "Hello"
```

This path starts the separately installed internal `arbora-acp` executable at
an absolute workspace root. It first checks beside the resolved `tuig` binary,
including when a symlink starts `tuig`. Only an absent sibling
permits lookup on `PATH`. An invalid sibling fails closed, without a second
lookup. Install directories and `PATH` must contain trusted executables. It does not start another frontend. Provider
credentials stay in the child environment; the central `AGENT_BEARER_TOKEN`
is not forwarded. Central Arbora remains the default, with no automatic fallback.

Local mode currently requires a POSIX host. It supports one text turn of at
most 16 KiB. The encoded request must also fit the backend's 64 KiB frame limit. The backend owns the model and history.
The client grants no file, terminal or permission capabilities. Ctrl+C requests
cancellation, then closes or stops and reaps the owned child. Output uses
nonblocking writes so an unread pipe cannot block cancellation. Initialization is
bounded to 30 seconds and the exchange to 330 seconds. Backend failure details
are not printed, to avoid exposing credentials. Local mode cannot observe an
existing task or resume a durable session. Installed Arbora/AU pairing remains
unqualified; do not treat the scripted tests as a released runtime receipt.
