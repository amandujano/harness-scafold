---
name: unit-testing
description: "Trigger: unit test, jest spec, *.spec.ts, test cases, TEST-CASES.md, coverage for a NestJS module. Catalog-first unit testing for this Jest + NestJS repo."
license: Apache-2.0
metadata:
  author: anmandu
  version: "1.0"
---

## Activation Contract

Load when writing, editing, or reviewing `*.spec.ts` files, when adding/changing
behavior in a `src/` module that needs test coverage, or when asked to plan test
cases for a module.

## Hard Rules

- Every module under test has a plain-text `TEST-CASES.md` beside its source. It
  is the source of truth and is written/updated **before** the matching specs.
- Each spec `it(...)` title MUST match a `TEST-CASES.md` entry verbatim. The
  catalog and the specs stay 1:1.
- Unit tests do no real I/O: mock `ConfigService`, `jose`, `@supabase/supabase-js`,
  global `fetch`, and HTTP. A test that hits the network is a bug.
- Cover happy path + every error path + edge cases (empty, malformed, missing
  header, expired, boundary values) for each unit.
- Specs live beside source as `*.spec.ts` (`rootDir: src`). Do not add e2e here.
- Keep tests deterministic — no clocks, randomness, or ordering assumptions
  unless faked.

## Decision Gates

| Unit under test | Setup |
|---|---|
| Pure provider (deps are constructor args) | `new Service(fakeDep)` — no `TestingModule` |
| Needs Nest DI graph, guards, or pipes | `Test.createTestingModule().overrideProvider()` |
| Controller | instantiate with a mocked service; assert delegation, status, mapping |
| Guard / interceptor | hand-build a fake `ExecutionContext`; mock `Reflector` |
| DTO | `plainToInstance` + `validate`; assert constraint keys |

## Execution Steps

1. Open the module's `TEST-CASES.md` (create from `assets/test-cases-template.md`
   if absent). Add or adjust entries for the target behavior first.
2. For each unchecked `[ ]` entry, write one `it()` with the identical title.
3. Mock all I/O boundaries; assert the collaborator was called as expected.
4. Run `yarn jest <path/to/file.spec.ts>`, then `yarn test`. Keep green.
5. Tick `[x]` in `TEST-CASES.md` for each implemented case.
6. Report coverage with `yarn test:cov` when the module is complete.

## Output Contract

Return:
- `*.spec.ts` files created/modified (colocated with source).
- `TEST-CASES.md` updated, entries checked off, titles matching `it(...)`.
- Test run result (pass/fail counts) and any entries deliberately deferred, with
  reason.

## References

- `assets/test-cases-template.md` — blank catalog format.
- `../../../src/auth/TEST-CASES.md` — worked example for the auth module.
- `../../../CLAUDE.md` — "Testing layout" and module conventions.
