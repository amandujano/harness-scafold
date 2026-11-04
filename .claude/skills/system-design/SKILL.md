---
name: system-design
description: "Trigger: a feature crosses a module boundary, adds a dependency, stores data, calls an external system, or the design is unclear. Reason about boundaries, data flow, tradeoffs and failure."
license: Apache-2.0
metadata:
  author: anmandu
  version: "1.0"
---

## Activation Contract

Load when a design choice is expensive to reverse: a new boundary, a data model, an
external dependency, or a concurrency question. Skip it for a change inside one module.
`.harness/docs/architecture.md` is the project's rule and wins over this advice.

## Checklist

1. **Boundaries.** What owns this behaviour? What must not know about it?
2. **Data flow.** Trace one request from entry to storage and back. Where is the data
   validated, and where is it trusted?
3. **Tradeoffs.** State what each option costs, not only what it gives.
4. **Failure modes.** For each external call: what if it is slow, down, or wrong? What
   does the caller see? Is a retry safe?
5. **State.** What must stay consistent, and what happens if the process dies halfway?
6. **Discarded alternative.** Name at least one option you rejected, and why.

## When Not to Add Complexity

- Do not add a layer, interface or queue for a need that does not exist yet.
- One implementation needs no abstraction.
- Prefer the boring option when the requirements do not demand more.
- If you cannot name the failure a mechanism prevents, leave it out.

## Output Contract

The decision, the alternative rejected and the failure modes, in `design.md` for a spec
or in your proposal to the human for the leader.
