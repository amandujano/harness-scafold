# Architecture — What "Doing a Good Job" Means

> This document defines the quality standard. The reviewer evaluates code against
> it. Principles here apply to any stack; add project decisions at the end.

## Principles

1. **Dependencies point inward.** Business rules do not depend on frameworks,
   databases or transport. Infrastructure depends on the domain, never the reverse.

2. **Clear boundaries.** Keep interface, domain and persistence concerns apart. Do
   not add a layer without a concrete reason recorded in the feature's spec.

3. **Explicit errors.** Failures use the language's error mechanism with meaningful
   names or types. Do not signal failure with null values or silent defaults.

4. **Immutability by default.** Prefer values that do not change. Mutate only where
   the design requires it.

5. **Atomic persistence.** A failed write must not leave data half-written.

6. **Justified dependencies.** Each new external dependency needs a reason in the
   spec. Prefer the standard library when it does the job.

## What NOT to Do

- Do not mix I/O with domain logic.
- Do not hide failures: log to the proper stream and return a failure result.
- Do not add configuration systems, abstractions or extension points before a
  feature needs them.

## Project Decisions

Record decisions specific to this project here: required layers, data store,
dependency policy, external services. If it is not written here or in a spec, it
is not a requirement.

_None yet._
