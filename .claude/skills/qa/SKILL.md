---
name: qa
description: "Trigger: reviewing a feature or debt, judging tests, verifying acceptance or R<n>. A QA checklist for proving behaviour rather than trusting green tests."
license: Apache-2.0
metadata:
  author: anmandu
  version: "1.0"
---

## Activation Contract

Load when reviewing. `harness check` already proves the mechanical items; this checklist
is the judgment it cannot make.

## Checklist

Work through every item. Cite the file and line for each failure.

**Coverage**
- [ ] Each `R<n>` or `acceptance` item has a test that exercises that behaviour.
- [ ] The test would fail if the requirement were false. Mentally break the code: does
      any test notice?

**Test quality**
- [ ] Assertions check concrete results, not merely that nothing threw.
- [ ] The test exercises the real unit, not a mock of it.
- [ ] Mocks stop at real boundaries such as network and clock.
- [ ] Tests do not depend on order, time or shared state.
- [ ] No focused or skipped tests remain.

**Edge and failure cases**
- [ ] Empty, missing, malformed and boundary inputs are covered where they can occur.
- [ ] Each error path the spec names has a test asserting the concrete error.
- [ ] Failures leave state consistent.

**Exploratory checks**
- [ ] Run the feature once for real if you can, using something other than the test data.
- [ ] Try the input a hurried user would send.
- [ ] Look at what the diff changes that no test touches.

**Honesty of the work**
- [ ] Every shortcut visible in the diff has a debt entry.
- [ ] The implementation report matches what the code does.

## Output Contract

A verdict in the format in your agent definition. Any failed item is a required change.
