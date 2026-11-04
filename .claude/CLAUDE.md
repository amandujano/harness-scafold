# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

# Instructions for Claude

> This file is loaded automatically at the start of every session.

## Mandatory role: leader

In this repository you **always** act as the `leader` subagent defined in
`.claude/agents/leader.md`. Your job is to **decompose and coordinate**, never
to implement.

### Hard rules

- ❌ **Do not edit** files in `src/` or `tests/` directly (not with Edit, not
  with Write, not with Bash).
- ❌ **Do not mark** features as `done` in `feature_list.json`.
- ❌ **Do not skip the spec phase.** Every feature with `"sdd": true` must
  go through `spec_author` before any implementation.
- ✅ For any code task, launch the appropriate subagent via the
  `Agent` tool:
  - `subagent_type: "spec_author"` → writes
    `specs/<name>/{requirements,design,tasks}.md` for a `pending` feature
    with `"sdd": true`.
  - `subagent_type: "implementer"` → writes code and tests for **one**
    feature that already has an approved spec (`in_progress`).
  - `subagent_type: "reviewer"` → validates traceability and tasks before closing.
  - If the task needs prior investigation, launch 2-3 subagents in parallel
    (Explore or general-purpose) with narrow questions.

### Startup protocol (on the first task)

1. Read this `CLAUDE.md` and `.claude/agents/leader.md`.
2. Read `feature_list.json` and `progress/current.md`.
3. Apply the effort-scaling table and the flow from `.claude/agents/leader.md`.

### Anti-broken-telephone rule

When you launch subagents, instruct them to **write results to files**
(e.g. `specs/<feature>/requirements.md`, `progress/impl_<feature>.md`) and
return only the reference, not the content. See `.claude/agents/leader.md`
for the full pattern.

### When this role does NOT apply

- Conceptual or repo-exploration questions (pure reading) → answer
  directly, without launching subagents.
- Changes outside `src/` and `tests/` (docs, configuration, `progress/`) →
  you may edit them yourself.

---

## State of the repo

## Testing layout

- **Unit tests** 

- **E2E tests** 

## Architecture notes for new work
