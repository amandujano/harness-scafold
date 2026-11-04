# AGENTS.md — Navigation Map for AI Agents

> This file is a **map**, not a rule bible. Read only what you need when you need
> it. Paths are relative to the project root.
>
> The lifecycle, the role permissions and the invariants are defined once, in
> `.harness/rules.json`. `.harness/bin/harness` evaluates them. If any prose
> disagrees with that file, the file wins.

## 1. Before Starting

1. Read the session briefing. Claude Code injects it at session start; to see it
   again, run `.harness/bin/harness resume`.
2. Run `.harness/bin/harness check`. If it fails, **stop** and resolve it.
3. Run `.harness/bin/harness next`. It prints the one legal next action.
4. Read `.harness/docs/specs.md` before touching any spec or `sdd: true` feature.

## 2. Repository Map

| Path | Content | When to read |
|---|---|---|
| `src/` | The whole application: manifest, code and tests | To implement |
| `.harness/manifest.json` | Hashes of harness files as installed, used by `harness update` | Never by hand |
| `.harness/config.json` | Stack and test, build and lint commands, run from `src/` | Before running commands |
| `.harness/rules.json` | States, transitions, role permissions, invariants | When a rule is unclear |
| `.harness/state/feature_list.json` | Features and their status | Always |
| `.harness/state/techdebt_list.json` | Ledger of shortcuts taken by agents | Always; and whenever you take a shortcut |
| `.harness/state/tasks.json` | Tasks started, written only by `harness task start` | Never by hand |
| `.harness/progress/current.md` | Current session state | Always |
| `.harness/progress/history.md` | Append-only log of previous sessions | For historical context |
| `.harness/specs/<feature>/` | `requirements.md`, `design.md`, `tasks.md` | Before implementing an `sdd: true` feature |
| `.harness/docs/architecture.md` | What "doing a good job" means here | Before implementing |
| `.harness/docs/conventions.md` | Shared style rules | Before writing code |
| `.harness/docs/stack/` | Conventions and testing guide for this stack; `harness init` creates it, so it does not exist in the scaffold itself | Before writing code or tests |
| `.harness/docs/specs.md` | SDD process and EARS notation | Before drafting or reading a spec |
| `.harness/docs/verification.md` | How to prove the work functions | Before closing a task |
| `.harness/docs/model_strategy.md` | Which model each agent runs on and why | Before changing an agent's `model:` |
| `.harness/CHECKPOINTS.md` | Criteria for a correct final state, generated from `.harness/rules.json` | For self-evaluation |
| `.claude/agents/` | `leader`, `spec_author`, `implementer`, `reviewer` | If orchestrating work |

## 3. Hard Rules

- **One feature at a time.** Do not mix changes from several features.
- **Status changes only through `harness transition`.** Never edit it by hand.
- **Spec approval is human.** Only a person runs `harness approve`.
- **Project maintenance is human.** Only a person runs `harness update` and
  `harness ci github`.
- **Do not close a feature without green tests.** The `done` transition enforces it.
- **Document what you do** in `.harness/progress/current.md` while working.
- **Declare every shortcut** in `.harness/state/techdebt_list.json` the moment you
  take it. An undeclared shortcut is a rejection. Never remove a debt entry.
- **If you don't know something, look in `.harness/docs/`** before inventing it.

## 4. Workflow

`harness next` drives the flow. In outline:

```
sdd: true    pending → [spec_author] → spec_ready → ⏸ human approve → in_progress
sdd: false   pending → in_progress
both         in_progress → [implementer → reviewer] → done
```

`CHANGES_REQUESTED` keeps the feature `in_progress` and loops implementer →
reviewer until `APPROVED`. The leader then runs `harness transition <name> done`.

To pay a debt in place, the leader runs `harness debt start <name>`, the same
implementer and reviewer loop follows, and `harness debt resolve <name>` closes it.
Only one feature or debt is active at a time.

## 5. Recovery

**What survives an interruption:** everything on disk, meaning feature and debt
status, specs, reports, the log, and which task was started and not ticked.

**How to resume:** start a session. The briefing names the active work and any task
in flight, and `harness next` says `implementer: resume <feature> at T3`. The leader
asks the human whether to resume or to block.

**Limits:** uncommitted code in `src/` is not a restore point: it is whatever the
interrupted task left, possibly half-written. Read it before continuing. Committing
per task is a human decision and is not automated.

## 6. Session Closure

1. Run `.harness/bin/harness check`: it must pass.
2. Confirm no `critical` debt is `open`; if there is, the session does not close.
3. Move the summary from `.harness/progress/current.md` to the end of
   `.harness/progress/history.md`.
4. Reset `current.md` from `.harness/templates/progress_current.md`.
5. Do not leave temporary files, debug output, or contextless TODOs.

## 7. If You Get Stuck

- Reread the relevant file in `.harness/docs/`.
- If a tool does not do what you expect, or the hook blocks you, **do not invent a
  workaround**: document the blocker in `.harness/progress/current.md` and stop.
