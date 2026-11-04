# Stack Testing — Python

Commands come from `.harness/config.json` and run in `src/`.

- Tests live in `src/tests/` as `test_<module>.py`.
- One `Test<Thing>(unittest.TestCase)` class per logical unit.
- Use `tempfile.TemporaryDirectory()` for files instead of filesystem mocks.
- Descriptive names: `test_load_returns_empty_when_file_missing`.

Test catalog titles match the test method name.
