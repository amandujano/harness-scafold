# Code Conventions

> Extreme homogeneity. AI predicts better when the repository looks
> the same everywhere.

## Python Style (change to another language)

## File Structure

## Tests

- One test file per module: `tests/test_<module>`.
- One `Test<Thing>(unittest.TestCase)` class per logical unit.
- Each test uses a `tempfile.TemporaryDirectory()` and cleans up after itself.
- Descriptive test names: `test_load_returns_empty_when_file_missing`.

## Error Handling

## Comments

By default, they are **not** written. They are only allowed when explaining a
non-obvious *why* (e.g., documented workaround, subtle invariant). Names should
do the rest.
