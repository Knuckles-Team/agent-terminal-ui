# Tuig constitution

This repository inherits the [organization constitution](https://github.com/Knuckles-Team/pipelines/blob/main/.specify/memory/constitution.md) version 1.0.0. Every article of that constitution applies here. This file adds only the rules and limits of this repository.

**Inherits**: organization constitution v1.0.0 | **Version**: 1.0.0 | **Ratified**: 2026-10-31 | **Last amended**: 2026-10-31

## Organization standards

- [Spec standard](https://github.com/Knuckles-Team/pipelines/blob/main/reference/spec-standard.md): one owning spec per capability, computed states, `Spec:` trailers.
- [Ecosystem boundaries](https://github.com/Knuckles-Team/pipelines/blob/main/reference/ecosystem-boundaries.md): which repository owns which requirement.
- [Wording standard](https://github.com/Knuckles-Team/pipelines/blob/main/reference/ste.md): sentences of 20 words or fewer, with `must`, `should`, or `may`.

## Repository articles

### R-I. One native terminal frontend

Tuig is one native Rust terminal frontend for arbora. The package index distributes the executable. Python supports developer validation only and provides no runtime interface, compatibility frontend or launcher.

**Enforced by:** Rust tests, `cargo clippy` and `cargo fmt`; the repository pre-commit checks.

**Plan check:** Does the change keep the runtime native, with no Python runtime path?

### R-II. Arbora owns the task lifecycle

Tuig owns terminal presentation and operator input. Arbora owns the served task lifecycle, authentication, authorization and operations. Tuig never implements a second agent or tool executor.

**Enforced by:** [Ecosystem boundaries](https://github.com/Knuckles-Team/pipelines/blob/main/reference/ecosystem-boundaries.md), tuig row and forbidden-import matrix.

**Plan check:** Does the change reach every operation through arbora?

### R-III. Approval fails closed and mutations are not replayed

Approval fails closed when unavailable. An unknown mutation outcome is never replayed automatically. Task, context and run identities stay distinct. Remote cancellation needs explicit confirmation.

**Enforced by:** The `terminal-runtime` spec rows and their bound Rust tests.

**Plan check:** Does the change refuse on unavailable approval and never replay an unknown outcome?

### R-IV. Terminal access is preserved

Every view works with the keyboard alone, responds without blocking input, supports no-color mode and stays bounded in size.

**Enforced by:** The `terminal-runtime` spec rows and their bound Rust tests.

**Plan check:** Does the new view work by keyboard, in no-color mode, within bounded size?

## Repository limits

This repository sets no numeric limit of its own. It follows the organization limits table.

Amend this file in a reviewed change. State the impact in the pull request. When the organization constitution changes its version, update the **Inherits** line in the same change.
