# Spec Driven Development (SDD)

> This project follows a Kiro-style flow: requirements → design → tasks → code.
> Code is not written until the spec is approved by a human.

## Structure

Every new feature (`"sdd": true` in `feature_list.json`) has a dedicated folder
as soon as it leaves `pending`:

```
specs/<feature-name>/
├── requirements.md   # WHAT is needed (EARS notation)
├── design.md         # HOW it will be built (technical decisions)
└── tasks.md          # Concrete STEPS to implement
```

The `feature-name` matches the `name` field in `feature_list.json`.

## Feature States

| State         | Meaning                                                       |
|----------------|---------------------------------------------------------------|
| `pending`      | No spec. The `spec_author` is the first to act.               |
| `spec_ready`   | Spec drafted. Awaiting human approval. NO code is touched.    |
| `in_progress`  | Spec approved. `implementer` working.                         |
| `done`         | Code green, `reviewer` approved, session closed.             |
| `blocked`      | Stuck. Reason in `progress/current.md`.                      |

## The Human Approval Gate

The automatic flow stops **once**: when the `spec_author` finishes
their three files, marks the feature as `spec_ready`, and stops. The human
reads `specs/<feature>/` and says "approved" (or requests changes).

Only then does the `leader` transition `spec_ready → in_progress` and launch
the `implementer`.

```
pending → [spec_author] → spec_ready → ⏸ HUMAN → in_progress → [implementer → reviewer] → done
```

## requirements.md — Strict EARS

Requirements are written in **EARS** (Easy Approach to Requirements
Syntax). Each requirement is a numbered paragraph using one of these five
patterns:

| Pattern         | Template                                                    |
|----------------|-------------------------------------------------------------|
| **Ubiquitous** | `The system SHALL <action>.`                               |
| **Event**       | `WHEN <trigger>, the system SHALL <action>.`               |
| **State**       | `WHILE <state>, the system SHALL <action>.`                |
| **Optional**    | `WHERE <optional feature>, the system SHALL <action>.`     |
| **Unwanted**    | `IF <unwanted event> THEN the system SHALL <action>.`    |

Hard Rules:

- Each requirement has a stable ID: `R1`, `R2`, ...
- Each requirement MUST be verifiable by at least one concrete test.
- Do not mix several `SHALL`s in a single requirement. If there is more than one, split it.
- Do not use soft verbs ("could", "can", "supports"). Only `SHALL` / `SHALL NOT`.

Example:

```markdown
## R1
WHEN the user executes `python -m src.cli recent`, the system SHALL
print up to 5 notes ordered by `created_at` descending.

## R2
IF the `--limit` flag receives a value <= 0 THEN the system SHALL
print an error message to stderr and exit with a non-zero code.
```

## design.md — Technical Decisions

Captured **before** touching code:

- Which files are created / modified.
- Which new signatures appear (functions, classes, commands).
- Which exceptions are reused or added.
- Which alternative was discarded and why (at least one).

This is NOT first-principles engineering — rely on
`docs/architecture.md` and `docs/conventions.md`. The `design.md` documents the
points where your feature touches the boundary of those rules.

## tasks.md — Executable Checklist

Discrete steps in order, each with a checkbox. Each task references at
least one `R<n>` it covers.

Example:

```markdown
- [ ] T1 — Add `cmd_recent` in `src/cli.py`. Covers: R1, R3.
- [ ] T2 — Register `recent` subparser with `--limit` flag. Covers: R1, R2.
- [ ] T3 — Add `test_recent_default_limit` in `tests/test_cli.py`. Covers: R1.
- [ ] T4 — Add `test_recent_invalid_limit` in `tests/test_cli.py`. Covers: R2.
```

The `implementer` marks `[x]` each task upon completion. The `reviewer`
rejects if any `[ ]` remains without documented justification.

## Traceability (Hard Rule)

- Each test in `tests/` must be mappable to an `R<n>` in its spec.
- Each `R<n>` must have at least one concrete test.
- The `reviewer` explicitly checks this correspondence and rejects
  if it's missing.

The `implementer` documents the map in `progress/impl_<name>.md`:

```markdown
## Traceability
- R1 → `test_recent_default_limit`
- R2 → `test_recent_invalid_limit`
- R3 → `test_recent_custom_limit`
```

## When SDD Does NOT Apply

Features with `"sdd": false` or without the `sdd` field (legacy 1–6) DO NOT
have a spec. SDD only applies moving forward.
