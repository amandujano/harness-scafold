<!-- harness-scaffold-readme -->
# AI Development Harness

A scaffold for building software with Claude Code as a coordinated team of agents:
**leader**, **spec_author**, **implementer** and **reviewer**. Code is not written
until a human approves a spec, and work is not closed until tests prove it.

Its key property: the rules are **executed, not just described**. The lifecycle and
role permissions live in one file, and a CLI and a Claude Code hook enforce them
outside the model.

This harness is for Claude Code only.

## Requirements

- Python 3.9 or newer, used by the `harness` CLI (standard library only).
- Git.
- The toolchain of your stack. `harness init` checks it before changing anything.

## Install

From a clone of this repository:

```bash
.harness/bin/harness install     # symlinks harness into ~/.local/bin
```

Use `--bin-dir DIR` for another location.

## Create a Project

```bash
harness stacks                   # list available stacks
harness init nest my-api         # or: go, java, python, generic
cd my-api
claude
```

`harness init <stack> [path] [--name NAME] [--no-scaffold]` generates the application
in `src/` with the stack's own tools, installs the harness, configures the test,
build and lint commands, merges `.gitignore`, runs `git init` when needed, and then
validates the result. It never commits and never overwrites your README. It refuses
a non-empty `src/` or an already initialized project. Setting `stack` in
`.harness/config.json` is its last step: any failure, `SIGTERM` or `SIGHUP` before that
undoes what the run created, so you can fix the cause and retry.

| `init` exit code | Meaning |
|---|---|
| `0` | Initialized, and the check passed |
| `1` | Not initialized; nothing was left behind |
| `3` | Initialized, but the check failed. Fix the problems; do not run `init` again. `generic` returns this until `commands.test` is set |

If `init` is killed outright, it leaves `.harness-init-manifest.json` in the target.
Run `init` again: it rolls back exactly the paths listed there, says so, and continues.

| Stack | Generates | Needs |
|---|---|---|
| `nest` | `nest new` (npm, Jest) | `nest` or `npx`, `npm` |
| `go` | `go mod init` and a small tested program | `go` |
| `java` | Maven quickstart archetype | `mvn`, `java`; network on first use |
| `python` | `pyproject.toml`, package and `unittest` test | `python3` |
| `generic` | Nothing | Set `commands.test` in `.harness/config.json` |

You can also run `.harness/bin/harness init <stack>` inside a fresh clone to turn
that clone into the project. Its `.harness/tests/` and other stacks remain until you
delete them.

## Project Layout

```
.claude/     Claude Code configuration: instructions, agents, skills, hook wiring
.harness/    The process: rules, state, specs, reports, docs. Not application code
src/         The whole application: manifest, code and tests
```

`.harness/manifest.json` records the harness files as installed, so `harness update`
can tell them from your edits. `.github/workflows/harness.yml` exists only after you
run `harness ci github`.

`.claude/` stays outside `.harness/` because Claude Code loads agents and settings
from fixed locations. A generated `.harness/` is slim: from `stacks/` it keeps only its
`stack.json`, the guides live in `.harness/docs/stack/`, and from `templates/` it keeps
only the session template. Stack commands run from `src/`, so frameworks keep their usual
layout one level down, such as `src/src/main.ts` in Nest and `src/pom.xml` in Maven.

## Daily Flow

1. Describe what you want in Claude Code. The leader writes features to
   `.harness/state/feature_list.json`.
2. The leader follows `harness next`, which prints the one legal next action.
3. `spec_author` writes `.harness/specs/<feature>/`, and the flow stops.
4. Read the spec, then approve it **from your own terminal**:

   ```bash
   harness approve <feature>
   ```

5. `implementer` builds, `reviewer` approves or requests changes, and the leader
   closes the feature with `harness transition <feature> done`.

| Command | Purpose |
|---|---|
| `harness check [--no-tests]` | Validate state and invariants, and run tests |
| `harness next` | Print the one legal next action |
| `harness resume [--json]` | Print a fast, read-only briefing; never runs tests |
| `harness task start <feature> T<n>` | Implementer: record that a task has started |
| `harness debt start <name>` | Leader: start paying an `sdd: false` debt in place |
| `harness debt resolve <name>` | Leader: close a paid debt on its evidence |
| `harness checkpoints [--write]` | Print `.harness/CHECKPOINTS.md`, or regenerate it (human only) |
| `harness update [--dry-run] [--force]` | Update harness-owned files from the scaffold |
| `harness ci github [--force]` | Write the GitHub Actions workflow |
| `harness transition <feature> <state>` | Change a status, enforcing actor and guards |
| `harness approve <feature>` | Human approval: type the code shown on your terminal. Later spec edits invalidate it |

To resume a blocked feature, run this in your own terminal:

```bash
harness transition <feature> <previous-state> --as human
```

## Recovering From an Interruption

**What survives:** everything on disk: status, specs, reports, the log, and which task
was started and not ticked. `harness task start` records that outside agent discipline.

**How to resume:** start a new session. A `SessionStart` hook injects the `harness resume`
briefing, and `harness next` prints `implementer: resume <feature> at T3 (started, not
finished)`. The leader asks you whether to resume or to block.

**Limits:**

- Uncommitted code in `src/` is not a restore point. It is whatever the interrupted task
  left, possibly half-written.
- Committing per task is your decision; the harness does not automate it.
- The briefing skips tests and slow guards, so it says when `harness next` may differ.
- Tasks exist only for `sdd: true` features, so other work has no in-flight trace.

## Update a Project

Run the global `harness` from inside a project; it uses its own scaffold clone as the
source. Commit first: it refuses to start over uncommitted harness files.

```bash
harness update --dry-run         # print the plan and change nothing
harness update                   # add `--force` to overwrite local changes
```

`.harness/manifest.json` records what the last install wrote. An unchanged file is
replaced. A locally modified file is kept, and the incoming version lands beside it as
`<file>.new`. Without a manifest, every differing file counts as locally modified. Hook
entries in `.claude/settings.json` are merged, and your other settings stay. A failure
rolls everything back.

It updates the CLI, `rules.json`, the session template, the project's `stack.json`,
generic docs, agents and skills, and regenerates `.harness/CHECKPOINTS.md` from the
resulting rules. If it keeps your `rules.json`, merge `rules.json.new` by hand and run
`harness checkpoints --write`. Files an older project has beyond this are left alone.
It never touches `.harness/state/`, `specs/`, `progress/`, `approvals/`,
`config.json`, `src/`, `.claude/CLAUDE.md`, `.harness/docs/stack/`, `architecture.md` or
`conventions.md`. Only you run it: the hook blocks agents.

## Continuous Integration

```bash
harness ci github                # writes .github/workflows/harness.yml
```

The workflow runs on push and pull request, sets up the stack's toolchain, and runs
`harness check`. Each stack declares its setup under `ci` in `stack.json`. `generic`
declares none, so it tells you what to add. An existing workflow needs `--force`.

CI matters because the hook only governs Claude Code. CI is what audits approvals and
catches changes made outside it. Review changes to `.harness/approvals/` in pull
requests. Agents may not write `.github/workflows/`.

## How Rules Are Enforced

`.harness/rules.json` is the single source of truth for states, transitions, role
permissions and invariants. If prose disagrees with it, it wins.

`.claude/settings.json` runs `harness hook pre-tool-use` before Write, Edit,
MultiEdit, NotebookEdit and Bash, and `harness hook session-start` when a session
opens. The main conversation counts as `leader`. Paths are
compared case-insensitively. Agent types outside the four roles may write only what
`unknown_role_allow` lists, which excludes `src/`, `.harness/` and `.claude/`.

Evidence has one owner: only `reviewer` writes `.harness/progress/review_*`, and only
`implementer` writes `.harness/progress/impl_*`. A feature's `name` and `sdd` are
immutable for agents; a human edits them directly.

The debt ledger keeps every entry: no agent may remove one or mark it `resolved` by
hand. Only a human may lower, accept or drop a `critical` debt.

`harness approve`, `harness update` and `harness ci github` are for humans, and the
hook blocks agents from running them. Agents also cannot write `.github/workflows/`.

Global agents, such as `sdd-*`, are outside the four roles, so they are **read-only**
inside generated projects. Use the project's own agents there.

Paths in a stack's `generated` list, such as `dist` or `node_modules`, are writable by
the implementer through Bash, including at the project root. They can never match
`.harness`, `.claude` or `.git`.

Limits you should know:

- Bash inspection is a **guardrail, not a sandbox**. It catches common write patterns,
  not every possible command. Script bodies run by an interpreter are not inspected.
  Git operations that swap whole trees, such as switching branches and `git stash`, stay
  allowed even though they rewrite files. So do build tools and `xargs` with piped paths.
- **The human gate cannot fully stop a process running as your user.** `harness approve`
  reads a random code from `/dev/tty`, ignores stdin, and records who and when in
  `.harness/approvals/`. That guards against accidental and routine agent behaviour,
  not a determined adversary. Audit approvals in code review or CI.
- A hook that cannot start, such as with no `python3`, does not block anything: Claude
  Code only blocks on exit code 2. Rules that cannot be loaded do block.
- The hook governs Claude Code only. Your editor and terminal are not restricted.
- `harness check` confirms each requirement maps to a name that occurs in `src/`.
  Judging that the test is meaningful stays with the reviewer.
- The generated workflow has not yet run on GitHub, and recovery from an update killed
  midway is untested. Use `harness update --dry-run` first on an important project.

## Add a Stack

Create `.harness/stacks/<name>/` with these files. No CLI change is needed.

| File | Content |
|---|---|
| `stack.json` | `description`, `requires`, `scaffold`, `commands`, `no_tests`, `generated`, `gitignore`, `ci` |
| `conventions.md` | Language and framework rules for agents |
| `testing.md` | Test location, naming and how to run one test |
| `scaffold/` | Optional files copied into `src/`; `{{name}}` is replaced |

Use `.harness/stacks/go/stack.json` as a reference. In `no_tests`, list under
`exit_codes` any non-zero code your test tool really uses for "no tests", such as
`5` for `unittest` and `1` for Jest. A non-zero exit without a declared code is a
failure. Under `unless`, list output proving tests did run, so a multi-module build
with one empty module is not reported as having no tests.

## Developing the Harness

This repository has `"stack": null` in `.harness/config.json`, so it is the scaffold
itself and enforcement is off. Run its test suite with:

```bash
python3 -m unittest discover -s .harness/tests
```
