---
name: unit-testing
description: "Trigger: unit test, test cases, TEST-CASES.md, test coverage for a module. Catalog-first unit testing for any stack; stack details come from .harness/docs/stack/testing.md."
license: Apache-2.0
metadata:
  author: anmandu
  version: "2.0"
---

## Activation Contract

Load when writing, editing, or reviewing tests, when adding or changing behavior in
a `src/` module that needs test coverage, or when asked to plan test cases.

## Hard Rules

- Read `.harness/docs/stack/testing.md` first: it defines test location, naming and
  how to run one test. Full-suite commands are in `.harness/config.json`.
- Every module under test has a plain-text `TEST-CASES.md` beside its source. It is
  the source of truth and is written or updated **before** the matching tests.
- Each test title MUST match a `TEST-CASES.md` entry verbatim. Catalog and tests
  stay 1:1.
- Unit tests do no real network I/O. A unit test that hits the network is a bug.
- Cover the happy path, every error path and edge cases (empty, malformed, missing,
  expired, boundary values) for each unit.
- Keep tests deterministic: no clocks, randomness or ordering assumptions unless
  faked.

## Execution Steps

1. Open the module's `TEST-CASES.md` (create it from
   `assets/test-cases-template.md` if absent). Add or adjust entries first.
2. For each unchecked `[ ]` entry, write one test with the identical title.
3. Fake all network boundaries; assert the concrete result and that collaborators
   were called as expected.
4. Run the single test, then `commands.test` from `src/`. Keep it green.
5. Tick `[x]` in `TEST-CASES.md` for each implemented case.

## Output Contract

Return:
- Test files created or modified.
- `TEST-CASES.md` updated, entries checked off, titles matching the tests.
- Test run result (pass and fail counts) and any entries deliberately deferred, with
  the reason.

## References

- `assets/test-cases-template.md` — blank catalog format.
- `.harness/docs/stack/testing.md` — stack-specific rules.
