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
