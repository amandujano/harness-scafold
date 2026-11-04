---
name: ast-grep
description: "Trigger: structural code search, large mechanical refactors, checking a pattern across the code, tuning project code rules. Use ast-grep instead of text search when syntax matters."
license: Apache-2.0
metadata:
  author: anmandu
  version: "1.0"
---

## Activation Contract

Load when text search would give false matches or a refactor touches many call sites.
ast-grep is optional: if `ast-grep --version` fails, use normal search and say so. Do
not install it yourself.

## Search

Patterns are code with metavariables. `$A` matches one node and `$$$A` matches many.

```bash
ast-grep run --lang python -p 'def $NAME($$$ARGS): $$$BODY' src
ast-grep run --lang ts -p 'console.log($$$A)' src
```

## Refactor

Preview first, and apply only when the preview is right. Work inside `src/`.

```bash
ast-grep run --lang ts -p 'oldName($$$A)' -r 'newName($$$A)' src
ast-grep run --lang ts -p 'oldName($$$A)' -r 'newName($$$A)' --update-all src
```

Run the tests after any rewrite: a syntactic match does not prove a semantic one.

## Review

Use it to answer questions such as "is every call of this function guarded?". Project
rules live with the stack in `.harness/stacks/`, and `harness check` runs them from
`src/`. A finding fails the check. Humans tune those rules; agents do not edit them.

To silence one justified finding, add an `ast-grep-ignore` comment on the line above it
and explain why in the report.
