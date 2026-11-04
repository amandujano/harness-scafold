---
name: feature-decomposition
description: "Trigger: turning human intent into features, writing acceptance criteria, splitting work, deciding what to ask. Decompose intent into the smallest shippable features."
license: Apache-2.0
metadata:
  author: anmandu
  version: "1.0"
---

## Activation Contract

Load when a human describes something they want built, or when a feature looks too big.

## Hard Rules

- One concern per feature. If the title needs "and", split it.
- Each feature ships on its own: it leaves the product working and adds something
  observable.
- Each `acceptance` item is a check a test can run: an input, a condition and an
  observable result. "Works well" and "is fast" are not acceptance.
- Never invent scope. Anything the human did not ask for is a proposal, not a feature.

## Ask or Propose

| Situation | Action |
|---|---|
| Two readings lead to different features | Ask one question, then stop |
| The answer changes the data model or a public contract | Ask |
| A sensible default exists and is cheap to reverse | Decide, and state it |
| You see a simpler design or a missing prerequisite | Propose it and let the human choose |
| The detail only affects implementation | Leave it to the spec |

## Execution Steps

1. Restate the intent in one sentence.
2. List the observable behaviours it needs.
3. Group them into the smallest features that each ship alone, prerequisites first.
4. Write `acceptance` for each. Set `"sdd": true` unless the change is mechanical.
5. Report what you wrote and what still needs an answer.

## Output Contract

Features appended to `.harness/state/feature_list.json` as `pending`, plus the open
questions. Rules on states are in `.harness/rules.json`.
