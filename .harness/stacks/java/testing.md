# Stack Testing — Java

Commands come from `.harness/config.json` and run in `src/`.

- Test classes mirror the production package and end in `Test`.
- Use JUnit assertions on concrete results.
- Use `@TempDir` for files.
- Run one class with `mvn -B test -Dtest=ClassName`.

Test catalog titles match the test method name or `@DisplayName`.
