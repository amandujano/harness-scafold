# Spec Driven Development (SDD)

> This project follows a Kiro-style flow: requirements → design → tasks → code.
> Code is not written until the spec is approved by a human.

## Structure

Every feature with `"sdd": true` in `.harness/state/feature_list.json` has a
dedicated folder as soon as it leaves `pending`:

```
.harness/specs/<feature-name>/
├── requirements.md   # WHAT is needed (EARS notation)
├── design.md         # HOW it will be built (technical decisions)
└── tasks.md          # Concrete STEPS to implement
```

The `feature-name` matches the `name` field in `.harness/state/feature_list.json`.

## Feature States

States and legal transitions are defined in `.harness/rules.json`, and statuses
change only through `harness transition`. `harness next` tells you what to do in
any state.

| State | Meaning |
|---|---|
| `pending` | Not started. |
| `spec_ready` | Spec drafted, awaiting human approval. No code is touched. |
| `in_progress` | `implementer` and `reviewer` are working. |
| `done` | Reviewer APPROVED and the check is green. |
| `blocked` | Stuck, with a `blocked_reason`. A human resumes it. |

## The Human Approval Gate

The automatic flow stops **once**: when `spec_author` finishes the three files and
moves the feature to `spec_ready`. The human reads `.harness/specs/<feature>/` and
either requests changes or approves from their own terminal:

```bash
.harness/bin/harness approve <feature>
```

You type a random code shown on your terminal. This records a hash of the spec, who
approved it and when in `.harness/approvals/<feature>.json`. Editing the spec
afterwards invalidates the approval; ticking tasks does not.

The hook denies agents this command, but a process running as your user cannot be
fully stopped. This guards against accidental and routine agent behaviour, not a
determined adversary, so audit approvals in code review or CI.

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
WHEN a client requests `GET /orders/recent`, the system SHALL return up to 5
orders sorted by `created_at` descending.

## R2
IF the `limit` parameter is less than 1 THEN the system SHALL respond with a
validation error that names the parameter.
```

## design.md — Technical Decisions

Captured **before** touching code:

- Which files are created / modified.
- Which new signatures appear (functions, classes, commands).
- Which exceptions are reused or added.
- Which alternative was discarded and why (at least one).

This is NOT first-principles engineering — rely on
`.harness/docs/architecture.md` and `.harness/docs/conventions.md`. The `design.md` documents the
points where your feature touches the boundary of those rules.

## tasks.md — Executable Checklist

Discrete steps in order, each with a checkbox. Each task references at
least one `R<n>` it covers.

`harness` checks this shape before a spec reaches you: `requirements.md` needs at
least one `## R<n>` heading, `tasks.md` at least one task, and every task must
reference an existing `R<n>`. Checkboxes inside code fences do not count.

Example:

```markdown
- [ ] T1 — Add the recent-orders query to the orders module. Covers: R1.
- [ ] T2 — Expose `GET /orders/recent` with a `limit` parameter. Covers: R1, R2.
- [ ] T3 — Add a test for the default limit. Covers: R1.
- [ ] T4 — Add a test for an invalid limit. Covers: R2.
```

The `implementer` marks `[x]` each task upon completion. The `reviewer`
rejects if any `[ ]` remains, and `harness transition <name> done` refuses it too.

## Traceability (Hard Rule)

- Each test written for the feature must be mappable to an `R<n>` in its spec.
- Each `R<n>` must have at least one concrete test.
- The `reviewer` explicitly checks this correspondence and rejects
  if it's missing.

The `implementer` documents the map in `.harness/progress/impl_<name>.md`:

```markdown
## Traceability
- R1 → `<test name>`
- R2 → `<test name>`
```

## When SDD Does NOT Apply

Features with `"sdd": false` have no spec and go straight from `pending` to
`in_progress`. The reviewer verifies them against their `acceptance` list.

## Example Entries

A feature in `.harness/state/feature_list.json`:

```json
{
  "id": 1,
  "name": "recent-orders",
  "title": "Recent orders endpoint",
  "description": "List the latest orders for the dashboard.",
  "acceptance": [
    "GET /orders/recent returns up to 5 orders, newest first",
    "A limit below 1 is rejected with a validation error"
  ],
  "sdd": true,
  "status": "pending"
}
```

A debt in `.harness/state/techdebt_list.json`:

```json
{
  "id": 1,
  "name": "recent-orders-error-path",
  "title": "Recent orders has no test for a failing data source",
  "description": "Only the happy path shipped. The error path exists but is untested.",
  "kind": "missing_test",
  "severity": "medium",
  "origin": { "agent": "implementer", "feature": "recent-orders", "task": "T3", "session": "2026-01-15" },
  "location": ["src/"],
  "interest": "Each change to this endpoint is unverified on its failure path.",
  "acceptance": ["A test asserts the concrete error response when the data source fails"],
  "sdd": false,
  "status": "open"
}
```

Valid debt values and moves are in the `debt` section of `.harness/rules.json`. A debt
is paid in one of two ways:

- **In place, for `"sdd": false`.** The leader runs `harness debt start <name>`, the
  implementer and reviewer work from its `acceptance`, and
  `harness debt resolve <name>` closes it on their evidence.
- **Promoted, for `"sdd": true`.** The leader copies it into the feature list as a
  `pending` feature with the same `name` and marks the debt `scheduled`. Closing that
  feature with `harness transition <name> done` resolves the debt in the same step.
