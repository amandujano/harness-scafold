# AI Development Harness Scaffold

This repository is a professional scaffold designed to coordinate the development of software using AI agents. It enforces a strict **Spec-Driven Development (SDD)** workflow to ensure that code is not written until requirements are clear, designed, and approved by a human.

## 🎯 Purpose

The goal of this harness is to eliminate "AI drift"—where the model iterates blindly without a stable target—by introducing formal specification and verification gates. It transforms the AI from a simple autocomplete tool into a structured team of specialized agents: **Leader**, **Spec Author**, **Implementer**, and **Reviewer**.

## 📂 Repository Structure

| Path | Purpose |
| :--- | :--- |
| `src/` | The application source code. |
| `tests/` | Automated test suite. |
| `specs/` | SDD artifacts: Requirements, Design, and Task lists per feature. |
| `docs/` | Project standards: Architecture, Conventions, and Verification rules. |
| `progress/` | Session tracking: `current.md` (active work) and `history.md` (archive). |
| `feature_list.json` | The source of truth for all features, their status, and SDD flags. |
| `AGENTS.md` | The navigation map for AI agents entering the project. |
| `init.sh` | Environment verification script (Must be green before any commit). |
| `CHECKPOINTS.md` | High-level objective criteria for the project's final state. |

## 🔄 The SDD Workflow

This harness enforces the following state machine for every feature marked `"sdd": true` in `feature_list.json`:

`pending` $\rightarrow$ `[spec_author]` $\rightarrow$ `spec_ready` $\rightarrow$ **⏸ HUMAN APPROVAL** $\rightarrow$ `in_progress` $\rightarrow$ `[implementer]` $\rightarrow$ `[reviewer]` $\rightarrow$ `done`

### 1. Specification Phase
The `spec_author` agent creates three files in `specs/<feature-name>/`:
- **`requirements.md`**: What the feature does (using EARS notation).
- **`design.md`**: How it's implemented (architecture, data flow, logic).
- **`tasks.md`**: A granular, ordered checklist for the implementer.

### 2. Human Gate
The workflow **stops** at `spec_ready`. A human must review the specs and provide a "Go" before the status is changed to `in_progress`.

### 3. Implementation & Verification
- The `implementer` executes the `tasks.md` checklist.
- The `reviewer` validates the implementation against the requirements and verifies that all tests pass.

## 🚀 Getting Started with this Scaffold

To start a new project using this harness:

1. **Clone/Copy the scaffold** into your project root.
2. **Configure `feature_list.json`**: Add your initial features and set `"sdd": true` for those requiring formal specs.
3. **Define Standards**: Update `docs/architecture.md` and `docs/conventions.md` to reflect your project's specific quality bars.
4. **Initialize**: Run `./init.sh` to verify your environment and test commands.
5. **Direct the AI**: Point your AI agent to `AGENTS.md` to let it understand its role and the workflow it must follow.

## 🛠 Maintenance

- **Environment Check**: Always run `./init.sh` before declaring a task `done`.
- **Progress Tracking**: Keep `progress/current.md` updated in real-time.
- **Cleanup**: Move summaries from `current.md` to `history.md` at the end of every session.
