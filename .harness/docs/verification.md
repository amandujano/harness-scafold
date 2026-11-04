# Verification — How to Prove the Work Functions

> Golden Rule: **the agent does not say "it works," they prove it**. Every feature
> ends with executable evidence, not claims.

## Verification Levels

### Level 1 — Automated Tests (Mandatory)

Every public unit in `src/` has at least one test that:

1. Covers the happy path.
2. Covers at least one error path if the unit can fail.

Run them with `commands.test` from `.harness/config.json`, or through:

```bash
.harness/bin/harness check
```

Test layout is in `.harness/docs/stack/testing.md`.

### Level 2 — Manual Smoke Test (Optional but Recommended)

Before closing the session, run one end-to-end flow by hand and record the result
in `.harness/progress/current.md`.

### Level 3 — Requirements Traceability (Mandatory for `"sdd": true`)

Each `R<n>` must map to at least one concrete test. The implementer documents the
map in `.harness/progress/impl_<name>.md`, one line per requirement, in this exact
form because `harness` reads it:

```markdown
## Traceability
- R1 → `<test name>`
- R2 → `<test name>`
```

`harness check` requires each mapped name to occur in `src/`.

For `"sdd": false`, the same report maps each `acceptance` item to a test, and the
reviewer verifies those. The report is required for every feature.

A feature closes only on evidence: an implementation report, and a review whose
latest verdict is `APPROVED` and which is not older than that report. Who may write
each report is in `.harness/rules.json`.

## Anti-patterns

- ❌ "I added the command, it should work." → missing executable test.
- ❌ A test that only verifies nothing was thrown. → check the concrete result.
- ❌ Mocking what could be exercised for real, such as the filesystem in a temp
  directory.
- ❌ Working around a failing guard. → fix the cause or stop.

## Final Verification

`.harness/bin/harness transition <name> done` runs the whole check and refuses to
close the feature if anything fails. If it is red, record the blocker in
`.harness/progress/current.md`.
