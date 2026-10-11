# TUI-RUNTIME design and integration plan

## Existing wiring and architecture

At the current public main revision, `CommandProcessor` in `agent_terminal_ui/commands.py` owns slash-command dispatch and the `/capabilities` and `/run` commands. `AgentClient` in `agent_terminal_ui/client.py` owns HTTP transport, session events and the older `/api/capabilities/*` and `/api/runs/*` routes. `agent_terminal_ui/app.py`, `screens/main.py`, `tui/input_text_area.py`, `tui/capability_palette.py` and `tui/run_inspector.py` are presentation consumers. This is the path to extend; no parallel command router, HTTP client or local GraphOS gateway should be created.

A TUI-RUNTIME-R001 implementation candidate exists on a separate Git branch, but it is not part of public main and does not establish release acceptance. It prototypes `/op`, `/confirm`, a lazy generated-client import and fail-closed approval behavior. Review and compose its exact changes rather than rebuilding the same transport from scratch. The current main package targets Python `>=3.11,<3.15`; GraphOS generated-client compatibility must be handled without raising that base floor silently.

```text
keyboard / slash command
    -> CommandProcessor
    -> AgentClient (one session, caller credential, HTTP/A2A transport)
    -> GraphOS versioned operation API or A2A plan confirmation
    -> server authorization, registry and effect gate
    -> typed result/error -> existing conversation and run widgets
```

## Contracts and decisions

| Boundary | Contract to implement or verify |
|---|---|
| Command input | `/op <registered-id> <JSON object>`; JSON is parsed once; a malformed or absent object is refused before any network call. `/confirm <opaque-plan-ref>` never accepts a caller-supplied substitute operation or parameters. |
| Generated operation client | Resolve `schema_for(op)` and `invoke(transport, op, params)` lazily. The installed registry digest must match the server. Missing package data or incompatible runtime yields `CLIENT_UNAVAILABLE`, not a fallback to an untyped endpoint. |
| HTTP operation | Use GraphOS's public versioned operation endpoint, caller-scoped authorization header, structured result and stable error envelope. No direct import of graph-os server internals or AU knowledge-graph internals. |
| A2A conversation | Reuse the GraphOS Agent Card and authenticated JSON-RPC task flow. Keep session/task identity on streaming and resumed turns; network errors must leave the UI responsive. |
| PLAN | Store only the short-lived server binding necessary for display and one confirmation. Bind to exact plan reference, op, input digest, caller/session, registry digest and expiry; let server make the final authoritative check. Clear after use or failure. |
| Approval | An `input-required` task is a pending request. Signed approval must be bound to the pending call and human authority in GraphOS. Until that public contract and served proof are present, refuse `approvals.*` and direct fleet-grant shortcuts. |
| Security | Require TLS and a verified credential for remote GraphOS. Do not emit bearer values to logs, widgets, saved sessions, test snapshots or exception strings. Local development endpoint rules must be explicit and bounded to loopback. |

## Compatibility and migration

Keep the TUI's base Python 3.11 chat install working. Put a generated GraphOS operation client behind a compatible optional extra or runtime capability check. Document the precise supported Python range in package metadata and lock. Where legacy capability/run APIs remain, inventory their callers and retire each only after a public replacement is served. The GeniusBot consumer must independently prove the same versioned envelope and identity rules. This repository only supplies its contract expectations.

## Quality and reuse

Use the existing command registry, `AgentClient`, `httpx`, Textual widgets, and GraphOS generated models. Keep one transport normalization path and no duplicated request envelope construction. Run the repository's configured Ruff, type and pytest checks. The current repository has no configured CCCC, `jscpd` or Dupehound command or threshold. Before acceptance, either add shared ecosystem invocations with an explicit baseline or record an agreed exception. Do not claim a numerical pass without a configured tool. Apply KISS through a single client and one-use confirmation state. No unrelated `/docs` edit is required. Update README/configuration only where command or credential setup changes, and update AGENTS/constitution only if the contract itself changes.

## Structure parity with agent-webui (2026-10-11)

The operator requires agent-terminal-ui to use the same structure as agent-webui. The table compares structure only.

| Element | agent-webui | agent-terminal-ui | Action |
|---|---|---|---|
| Specs | 6 area specs | 1 spec (`terminal-runtime`) | Decisions below; no new directory |
| Workflows | `advisory.yml`, `release.yml` | `pages.yml`, `pipeline.yml` | Differs in names; add release caller (R007) |
| Pages caller | `pages_pipeline.yml@main`, `spec_dashboard_enabled: true` | same | Same |
| Python pipeline caller | none seen | `python_pipeline.yml@main` | Keep |
| Pre-commit | `.config`/root config, 50+ hook ids incl. spec-standard, ste-staged, public-surface | root config, 26 ids | Add spec hooks (R004) |
| `pyproject` hook sections | `public_surface`, `ste` | none | Add (R006) |
| Packaged development skill | present | missing | Add (R003) |
| Docs | start, status, deployment, design-system, apps, atlas, others | agent_view, configuration, session pages | Add four pages (R005) |
| `mkdocs.yml` | present | present | Same |
| AGENTS.md | Commands, Quality gates, Branching, Documentation, Specs | Working discipline, worktrees, Specs | Add headings (R009) |

Area decisions, from the terminal code:

| webui area | Terminal client has it? | Decision |
|---|---|---|
| Design system | Yes: `app.py` selects a Textual theme (`tokyo-night`) | New rollup `TUI-RUNTIME-R008` in the existing spec |
| Decision evidence | Partly: `app.py` approval decisions, covered by `R001.5` | No new row |
| Finance asset manager | No: `git grep` for finance and asset finds nothing | No spec |
| API consumer | Yes: `client.py` GraphOS boundary, owned by `R001` and `R002` | No new row |
| App surfaces | Yes: `screens/`, owned by `R001.7` | No new row |
| Identity and access | Yes: bearer caller identity, owned by `R001.2` | No new row |

### Amendments

- 2026-10-11, rows `TUI-RUNTIME-R003` to `TUI-RUNTIME-R009`: the operator required agent-terminal-ui to match agent-webui structure. The old state had no structure rows. The new state adds seven rollups. Evidence: the comparison table above.
