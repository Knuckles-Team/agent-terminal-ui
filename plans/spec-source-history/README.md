# Spec source migration

The canonical requirements, tasks and decisions live in `specs/terminal-runtime/`.
These source records preserve their original bytes and historical claims.
Historical completion claims do not establish current delivery or acceptance.
Unchecked obligations remain open in the owning task file.

| Old path | Preserved source path | SHA-256 |
|---|---|---|
| `.specify/memory/constitution.json` | `plans/spec-source-history/memory/constitution.json` | `0418d31cb9505a481c5d137b399899ee3c0e0a4520777aff5f0a313e20154caf` |
| `.specify/reports/code_enhancement_report.md` | `plans/spec-source-history/analysis/code_enhancement_report.md` | `2ba4a62a4333f2dc616e7b1315e5a28e982ba224db4929489a3acac1a22074f6` |
| `.specify/reports/results.json` | `plans/spec-source-history/analysis/results.json` | `28ecaab72f6eedf75d3df249e5f05052dfb05472a32d36dc987e49dcd506521f` |
| `.specify/specs/code-enhancement-20260501/CHECKLIST.md` | `plans/spec-source-history/specs/code-enhancement-20260501/CHECKLIST.md` | `317f075a3f58fc99b33e936cf8cb0a82d70a43941782b96243886d9a9ba230e6` |
| `.specify/specs/code-enhancement-20260501/DRIFT_REPORT.md` | `plans/spec-source-history/specs/code-enhancement-20260501/DRIFT_REPORT.md` | `1df2d5943cd474127a4db85e7d06f765b46c74cfb87ea59f8d0e717aefd4a85d` |
| `.specify/specs/code-enhancement-20260501/spec.json` | `plans/spec-source-history/specs/code-enhancement-20260501/spec.json` | `caed209ec93cdbb9bdc3f424a0a06748916061d8425f09d02d9fce32e189266a` |
| `.specify/specs/code-enhancement-20260501/spec.md` | `plans/spec-source-history/specs/code-enhancement-20260501/spec.md` | `561be76b962dacb42b5340c3ee5b789b9a1aacc3657dd55b98298591d4024c92` |
| `.specify/specs/code-enhancement-20260501/tasks.json` | `plans/spec-source-history/specs/code-enhancement-20260501/tasks.json` | `d27f3c088479c3e01cc8f2f77e06bafe56bde21b4af1a0c3025d017f23285482` |
| `.specify/specs/code-enhancement-20260501/tasks.md` | `plans/spec-source-history/specs/code-enhancement-20260501/tasks.md` | `15911aadc5e68d3884619775d412ef9ea50bd81f2f98f1784c9a3a8469d361e7` |
| `.specify/tasks/fix_missing_client_methods.md` | `plans/spec-source-history/tasks/fix_missing_client_methods.md` | `6b75ee42736c10d0e7f9b44d8330fa860d1f72ebfeaa33f14e9e759da4be916a` |

The absent `.specify/specs/missing_client_methods.md` reference has no tracked source.
No source file was reconstructed from that reference.

## Canonical obligation map

Original priorities, estimates and statuses remain unchanged in the preserved JSON and Markdown.
Each mapped obligation remains unchecked. Counts and version suggestions are historical observations.
Current checks govern repairs; old version suggestions do not authorize dependency downgrades.

| Source obligation | Canonical requirement | Priority | Effort |
|---|---|---|---|
| `T001` | [TUI-RUNTIME-R015.1](../../specs/terminal-runtime/requirements.md) | P2-Medium | Medium |
| `T002` | [TUI-RUNTIME-R015.2](../../specs/terminal-runtime/requirements.md) | P1-High | Large |
| `T003` | [TUI-RUNTIME-R015.3](../../specs/terminal-runtime/requirements.md) | P1-High | Large |
| `T004` | [TUI-RUNTIME-R015.4](../../specs/terminal-runtime/requirements.md) | P1-High | Large |
| `T005` | [TUI-RUNTIME-R015.5](../../specs/terminal-runtime/requirements.md) | P2-Medium | Medium |
| `T006` | [TUI-RUNTIME-R015.6](../../specs/terminal-runtime/requirements.md) | P2-Medium | Medium |
| `T007` | [TUI-RUNTIME-R015.7](../../specs/terminal-runtime/requirements.md) | P2-Medium | Medium |
| `T008` | [TUI-RUNTIME-R015.8](../../specs/terminal-runtime/requirements.md) | P2-Medium | Medium |
| `T009` | [TUI-RUNTIME-R015.9](../../specs/terminal-runtime/requirements.md) | P2-Medium | Medium |
| `T010` | [TUI-RUNTIME-R015.10](../../specs/terminal-runtime/requirements.md) | P2-Medium | Medium |
| `T011` | [TUI-RUNTIME-R015.11](../../specs/terminal-runtime/requirements.md) | P2-Medium | Small |
| `T012` | [TUI-RUNTIME-R015.12](../../specs/terminal-runtime/requirements.md) | P2-Medium | Medium |
| `T013` | [TUI-RUNTIME-R015.13](../../specs/terminal-runtime/requirements.md) | P2-Medium | Small |
| `T014` | [TUI-RUNTIME-R015.14](../../specs/terminal-runtime/requirements.md) | P2-Medium | Small |
| `T015` | [TUI-RUNTIME-R015.15](../../specs/terminal-runtime/requirements.md) | P2-Medium | Small |
| `T016` | [TUI-RUNTIME-R015.16](../../specs/terminal-runtime/requirements.md) | P2-Medium | Small |
| `T017` | [TUI-RUNTIME-R015.17](../../specs/terminal-runtime/requirements.md) | P2-Medium | Small |
| `T018` | [TUI-RUNTIME-R015.18](../../specs/terminal-runtime/requirements.md) | P2-Medium | Medium |
| `T019` | [TUI-RUNTIME-R015.19](../../specs/terminal-runtime/requirements.md) | P2-Medium | Large |
| `T020` | [TUI-RUNTIME-R015.20](../../specs/terminal-runtime/requirements.md) | P2-Medium | Medium |
| `T021` | [TUI-RUNTIME-R015.21](../../specs/terminal-runtime/requirements.md) | P2-Medium | Medium |
| `T022` | [TUI-RUNTIME-R015.22](../../specs/terminal-runtime/requirements.md) | P2-Medium | Medium |
| `T023` | [TUI-RUNTIME-R015.23](../../specs/terminal-runtime/requirements.md) | P2-Medium | Large |
| `T024` | [TUI-RUNTIME-R015.24](../../specs/terminal-runtime/requirements.md) | P4-Enhancement | Medium |
| `T025` | [TUI-RUNTIME-R015.25](../../specs/terminal-runtime/requirements.md) | P4-Enhancement | Medium |
| `T026` | [TUI-RUNTIME-R015.26](../../specs/terminal-runtime/requirements.md) | P4-Enhancement | Small |
| `T027` | [TUI-RUNTIME-R015.27](../../specs/terminal-runtime/requirements.md) | P4-Enhancement | Small |
| `T028` | [TUI-RUNTIME-R015.28](../../specs/terminal-runtime/requirements.md) | P4-Enhancement | Medium |
| `T029` | [TUI-RUNTIME-R015.29](../../specs/terminal-runtime/requirements.md) | P2-Medium | Small |
| `T030` | [TUI-RUNTIME-R015.30](../../specs/terminal-runtime/requirements.md) | P4-Enhancement | Medium |
| `T031` | [TUI-RUNTIME-R015.31](../../specs/terminal-runtime/requirements.md) | P2-Medium | Small |
| `T032` | [TUI-RUNTIME-R015.32](../../specs/terminal-runtime/requirements.md) | P2-Medium | Medium |
| `T033` | [TUI-RUNTIME-R015.33](../../specs/terminal-runtime/requirements.md) | P2-Medium | Medium |
| `T034` | [TUI-RUNTIME-R015.34](../../specs/terminal-runtime/requirements.md) | P2-Medium | Large |
| `T035` | [TUI-RUNTIME-R015.35](../../specs/terminal-runtime/requirements.md) | P2-Medium | Medium |
| `T036` | [TUI-RUNTIME-R015.36](../../specs/terminal-runtime/requirements.md) | P2-Medium | Medium |
| `T037` | [TUI-RUNTIME-R015.37](../../specs/terminal-runtime/requirements.md) | P2-Medium | Small |
| `T038` | [TUI-RUNTIME-R015.38](../../specs/terminal-runtime/requirements.md) | P2-Medium | Medium |
| `T039` | [TUI-RUNTIME-R015.39](../../specs/terminal-runtime/requirements.md) | P2-Medium | Medium |
| `T040` | [TUI-RUNTIME-R015.40](../../specs/terminal-runtime/requirements.md) | P2-Medium | Medium |
| `T041` | [TUI-RUNTIME-R015.41](../../specs/terminal-runtime/requirements.md) | P2-Medium | Medium |
| `T042` | [TUI-RUNTIME-R015.42](../../specs/terminal-runtime/requirements.md) | P2-Medium | Medium |
| `T043` | [TUI-RUNTIME-R015.43](../../specs/terminal-runtime/requirements.md) | P2-Medium | Medium |
| `missing-client-methods checkbox 1` | [TUI-RUNTIME-R015.44](../../specs/terminal-runtime/requirements.md) | P3-Critical | Unestimated |
| `missing-client-methods checkbox 2` | [TUI-RUNTIME-R015.45](../../specs/terminal-runtime/requirements.md) | P3-Critical | Unestimated |
| `missing-client-methods checkbox 3` | [TUI-RUNTIME-R015.46](../../specs/terminal-runtime/requirements.md) | P3-Critical | Unestimated |
| `missing-client-methods checkbox 4` | [TUI-RUNTIME-R015.47](../../specs/terminal-runtime/requirements.md) | P3-Critical | Unestimated |
| `missing-client-methods checkbox 5` | [TUI-RUNTIME-R015.48](../../specs/terminal-runtime/requirements.md) | P3-Critical | Unestimated |
| `missing-client-methods checkbox 6` | [TUI-RUNTIME-R015.49](../../specs/terminal-runtime/requirements.md) | P3-Critical | Unestimated |
| `missing-client-methods checkbox 7` | [TUI-RUNTIME-R015.50](../../specs/terminal-runtime/requirements.md) | P3-Critical | Unestimated |
| `missing-client-methods next step 1` | [TUI-RUNTIME-R015.51](../../specs/terminal-runtime/requirements.md) | Preserved | Unestimated |
| `missing-client-methods next step 2` | [TUI-RUNTIME-R015.52](../../specs/terminal-runtime/requirements.md) | Preserved | Unestimated |
| `missing-client-methods next step 3` | [TUI-RUNTIME-R015.53](../../specs/terminal-runtime/requirements.md) | Preserved | Unestimated |
| `missing-client-methods next step 4` | [TUI-RUNTIME-R015.54](../../specs/terminal-runtime/requirements.md) | Preserved | Unestimated |
| `CHECKLIST non-FR checkbox 44` | [TUI-RUNTIME-R015.55](../../specs/terminal-runtime/requirements.md) | Preserved | Unestimated |
| `CHECKLIST non-FR checkbox 45` | [TUI-RUNTIME-R015.56](../../specs/terminal-runtime/requirements.md) | Preserved | Unestimated |
| `CHECKLIST non-FR checkbox 46` | [TUI-RUNTIME-R015.57](../../specs/terminal-runtime/requirements.md) | Preserved | Unestimated |
| `CHECKLIST non-FR checkbox 47` | [TUI-RUNTIME-R015.58](../../specs/terminal-runtime/requirements.md) | Preserved | Unestimated |
| `CHECKLIST non-FR checkbox 48` | [TUI-RUNTIME-R015.59](../../specs/terminal-runtime/requirements.md) | Preserved | Unestimated |
| `CHECKLIST non-FR checkbox 49` | [TUI-RUNTIME-R015.60](../../specs/terminal-runtime/requirements.md) | Preserved | Unestimated |
| `CHECKLIST non-FR checkbox 50` | [TUI-RUNTIME-R015.61](../../specs/terminal-runtime/requirements.md) | Preserved | Unestimated |
| `CHECKLIST non-FR checkbox 51` | [TUI-RUNTIME-R015.62](../../specs/terminal-runtime/requirements.md) | Preserved | Unestimated |
| `CHECKLIST non-FR checkbox 52` | [TUI-RUNTIME-R015.63](../../specs/terminal-runtime/requirements.md) | Preserved | Unestimated |
| `CHECKLIST non-FR checkbox 53` | [TUI-RUNTIME-R015.64](../../specs/terminal-runtime/requirements.md) | Preserved | Unestimated |
| `CHECKLIST non-FR checkbox 54` | [TUI-RUNTIME-R015.65](../../specs/terminal-runtime/requirements.md) | Preserved | Unestimated |
| `CHECKLIST non-FR checkbox 55` | [TUI-RUNTIME-R015.66](../../specs/terminal-runtime/requirements.md) | Preserved | Unestimated |
| `CHECKLIST non-FR checkbox 56` | [TUI-RUNTIME-R015.67](../../specs/terminal-runtime/requirements.md) | Preserved | Unestimated |
| `CHECKLIST non-FR checkbox 57` | [TUI-RUNTIME-R015.68](../../specs/terminal-runtime/requirements.md) | Preserved | Unestimated |
| `CHECKLIST non-FR checkbox 58` | [TUI-RUNTIME-R015.69](../../specs/terminal-runtime/requirements.md) | Preserved | Unestimated |

Canonical definitions: `specs/terminal-runtime/requirements.md`; work order: `specs/terminal-runtime/tasks.md`; acceptance: `specs/terminal-runtime/test-spec.md`.
FR identifiers map to the same numeric T identifiers. Source user stories and acceptance criteria remain preserved.

The current R012.4.2 failure contract supersedes the preserved empty-default proposal.
R015.44 through R015.47 retain those client obligations against current served contracts.
