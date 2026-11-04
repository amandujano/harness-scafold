# Code Conventions

> Extreme homogeneity. AI predicts better when the repository looks the same
> everywhere. Language-specific rules are in `.harness/docs/stack/conventions.md`.

## Structure

- The whole application lives in `src/`. Do not put application files elsewhere.
- Follow the framework's normal layout inside `src/`.

## Tests

- Test layout and commands are in `.harness/docs/stack/testing.md`.
- Use descriptive test names that state the behavior and the condition.
- Each test cleans up after itself.

## Comments

By default, they are **not** written. They are only allowed when explaining a
non-obvious *why* (a documented workaround, a subtle invariant). Names should do
the rest.
