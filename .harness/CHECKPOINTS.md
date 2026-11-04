# CHECKPOINTS — Final State Evaluation

> In multi-agent systems, the path is not evaluated; the destination is.
>
> **[auto]** items are enforced by `.harness/bin/harness check`: a passing check
> proves them, so do not re-judge them. The remaining items need judgment.

## C1 — The Harness is Complete

- [ ] **[auto]** Every file in `required_files` of `.harness/rules.json` exists.
- [ ] **[auto]** `.claude/settings.json` runs the harness PreToolUse and SessionStart
      hooks.
- [ ] **[auto]** `.harness/bin/harness check` exits 0.

## C2 — State is Consistent

- [ ] **[auto]** State files are valid and use only known statuses.
- [ ] **[auto]** At most one feature or debt is `in_progress`.
- [ ] **[auto]** Every `done` feature has an implementation report and a current
      APPROVED review.
- [ ] `.harness/progress/current.md` is empty or describes the active session.

## C3 — Code Respects Architecture

- [ ] `src/` only contains what `.harness/docs/architecture.md` and the specs plan.
- [ ] New dependencies are justified in the feature's spec.
- [ ] No debug output or contextless TODOs.

## C4 — Verification is Real

- [ ] **[auto]** `commands.test` is configured and passes.
- [ ] **[auto]** When a feature is `done`, the test command finds tests.
- [ ] Tests follow `.harness/docs/stack/testing.md` and assert concrete results.

## C5 — Session Closed Correctly

- [ ] No suspicious untracked files.
- [ ] `.harness/progress/history.md` has an entry for the last session.

## C6 — Spec Driven Development

- [ ] **[auto]** Every `sdd: true` feature past `pending` has its 3 spec files, with
      `R<n>` headings and tasks that reference them.
- [ ] **[auto]** Every `sdd: true` feature in `in_progress` or `done` has an approval
      that matches its current spec.
- [ ] **[auto]** Every `done` `sdd: true` feature has all tasks `[x]`.
- [ ] **[auto]** Every `R<n>` of a `done` feature maps to a test name that occurs in
      `src/`.
- [ ] Each mapped test really verifies its `R<n>`.
- [ ] `requirements.md` uses strict EARS (see `.harness/docs/specs.md`).

## C7 — Technical Debt is Declared, Not Hidden

- [ ] **[auto]** Every debt has verifiable fields: non-empty `acceptance`, and an
      `origin` naming agent, feature and session.
- [ ] **[auto]** No `critical` debt is `open`.
- [ ] **[auto]** Every `resolved` debt has current evidence or the feature that paid it.
- [ ] **[auto]** Every `scheduled` debt with `sdd: true` has a feature with the same
      `name` that is not `done`.
- [ ] Every `acceptance` item is genuinely verifiable.
- [ ] Every shortcut visible in the session's diff has a matching entry. A clean
      ledger next to a diff full of compromises is a **failing** checkpoint.

---

**How to use this file:** the reviewer goes through the items that need judgment
and rejects the work if any fails.

> **On C7:** an empty debt ledger is only credible when the diff is genuinely
> clean. A reviewer that never finds debt is either reviewing perfect work or not
> reviewing at all.
