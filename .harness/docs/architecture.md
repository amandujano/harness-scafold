# Architecture — What "Doing a Good Job" Means

> This document defines the quality standard. Reviewer agents
> evaluate code against this file. If it's not here, it's not a requirement.

## Principles

1. **Clear Layers.** The project has three layers and only three:
   - **Persistence Layer** — handles data storage (e.g., JSON on disk).
   - **Domain Layer** — contains the core business logic and domain models.
   - **Interface Layer** — provides the user interface (e.g., CLI, API).
   Do not introduce additional layers (services, repositories, ORMs) until
   there is a concrete reason documented in `feature_list.json`.

2. **No External Dependencies.** Use only the language's standard library. If a feature
   requires a dependency, it must first be discussed (state `blocked`).

3. **Explicit Errors.** Functions that can fail (e.g., ID doesn't exist,
   corrupt file) must raise named exceptions/errors; they should not return `null`/`None`.

4. **Immutability by Default.** Core domain entities should be immutable.
   Modifying an entity means creating a new instance with the updated values.

5. **Disk Atomicity.** Every write to the data store must be atomic (e.g., write to a
   temporary file and then move/replace the original). Never leave the file half-written.

## Data Flow

```
user  ─→  Interface Layer
              │
              ├─ constructs Domain Entity
              │
              └─→  Persistence Layer (Load/Save)
                       │
                       └─→  Data Store (in CWD)
```

## What NOT to Do

- Do not use generic print statements for errors. Use the standard error stream (stderr) and return a non-zero exit code.
- Do not mix I/O operations with domain logic inside the Domain Layer.
- Do not read/write the data store on every operation inside a loop.
  Load at the start, modify in memory, and save at the end.
- Do not add a complex configuration system. The data store path should be passed
  explicitly or use a default constant.
