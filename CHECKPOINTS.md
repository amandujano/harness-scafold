# CHECKPOINTS — Final State Evaluation

> In multi-agent systems, the path is not evaluated; the destination is.
> These are the objective checkpoints that a judge (human or AI) can use
> to decide if the project is healthy.

## C1 — The Harness is Complete

- [ ] The 4 base files exist: `AGENTS.md`, `init.sh`, `feature_list.json`,
      `progress/current.md`.
- [ ] The 3 docs exist: `docs/architecture.md`, `docs/conventions.md`,
      `docs/verification.md`.
- [ ] `./init.sh` finishes with exit code 0.

## C2 — State is Consistent

- [ ] At most one feature is `in_progress` in `feature_list.json`.
- [ ] Every `done` feature has associated tests that pass.
- [ ] `progress/current.md` is empty or describes the active session
      (contains no clutter from previous sessions).

## C3 — Code Respects Architecture

- [ ] `src/` only contains modules planned in `docs/architecture.md`.
- [ ] No external dependencies in `requirements.txt` (must be empty
      or not exist).
- [ ] No loose `print()` statements for debug, nor contextless TODOs.

## C4 — Verification is Real

- [ ] `tests/` has at least one test per module in `src/`.
- [ ] Tests use `tempfile.TemporaryDirectory()`, not fs mocks.
- [ ] run commant to execute tests and it must shows that all tests passed

## C5 — Session Closed Correctly

- [ ] No suspicious untracked files (`*.tmp`, outside of `.gitignore`).
- [ ] `progress/history.md` has an entry for the last session.
- [ ] The last worked-on feature is reflected in its correct state.

## C6 — Spec Driven Development

- [ ] Every feature with `"sdd": true` in state `spec_ready`, `in_progress`,
      or `done` has its folder `specs/<name>/` with the 3 files:
      `requirements.md`, `design.md`, `tasks.md`.
- [ ] `requirements.md` uses strict EARS (see `docs/specs.md`).
- [ ] Every `done` feature with `"sdd": true` has all its tasks marked
      `[x]` in `tasks.md`.
- [ ] Each `R<n>` from `requirements.md` is covered by at least one concrete
      test in `tests/`.

---

**How to use this file:** a reviewer agent (`.claude/agents/reviewer.md`)
goes through each checkbox, marks `[x]` or `[ ]`, and rejects the session closure
if any boxes in C1-C6 remain empty.
