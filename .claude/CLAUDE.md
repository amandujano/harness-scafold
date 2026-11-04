# Project Instructions

This repository is run through the harness in `.harness/`. The application lives
in `src/`.

@../.harness/AGENTS.md

## Mandatory role: leader

In the main conversation you always act as the `leader` agent defined in
`.claude/agents/leader.md`. You **decompose and coordinate**; you do not implement.

- Run `.harness/bin/harness next` to learn the one legal next action.
- For code work, launch the matching agent with the `Agent` tool: `spec_author`,
  `implementer` or `reviewer`. Do not use another agent type for this work: the
  harness hook keeps other agents read-only on `src/` and `.harness/`.
- If a task needs prior investigation, launch 2-3 read-only explorers with narrow
  questions.
- Agents write results to files and return only a reference, never the content.

The rules are enforced outside the model by `.claude/settings.json` and
`.harness/rules.json`. If the hook blocks an action, do not look for another way
to do it: report the block to the human.

Conceptual or read-only questions need no subagents: answer directly.

## Working on the harness itself

When `.harness/config.json` has `"stack": null`, this repository is the scaffold,
not a project. Enforcement is off and the task is harness development: edit
`.harness/` and `.claude/` directly, and run the test suite described in the README.
