---
name: ears-specs
description: "Trigger: writing or fixing requirements.md, design.md or tasks.md for a feature. Write verifiable EARS specs in the shape the harness enforces."
license: Apache-2.0
metadata:
  author: anmandu
  version: "1.0"
---

## Activation Contract

Load when writing a spec. The process and EARS patterns are in `.harness/docs/specs.md`;
read it first. This skill covers how to write a spec that passes.

## The Shape the Harness Enforces

`harness transition <name> spec_ready` refuses a spec that breaks these:

- All three files exist: `requirements.md`, `design.md`, `tasks.md`.
- `requirements.md` has at least one heading of the form `## R1`.
- `tasks.md` has at least one checkbox task: `- [ ] T1 — <step>. Covers: R1.`
- Every task references at least one existing `R<n>`.
- Checkboxes inside code fences do not count.

## Writing Requirements

- One `SHALL` per requirement. If there are two, split it.
- Every `acceptance` item maps to at least one `R<n>`.
- Ask of each one: what test would fail if this were false? If you cannot name one,
  rewrite it or stop with `blocked`.
- State the failure paths with the `IF ... THEN` pattern, not only the happy path.
- Name observable results, not implementation.
- Describe the system, not its test suite. Tests prove requirements; a requirement that
  says tests must exist has nothing of its own to verify.

## Writing the Design

Decide what the implementer would otherwise have to guess: files, signatures, errors,
and at least one discarded alternative with the reason. Load `system-design` when the
feature crosses a boundary.

## Writing Tasks

Small, ordered, each naming the file or unit it changes. A task for each test is fine;
`T<n>` numbers are stable because `harness task start` records them.

## Output Contract

The three files in `.harness/specs/<name>/`, each `R<n>` verifiable, each task traced.
