# Stack Testing — Go

Commands come from `.harness/config.json` and run in `src/`.

- Tests live beside the source as `*_test.go`.
- Prefer table-driven tests with `t.Run` for several cases.
- Use `t.TempDir()` for files and `httptest` for HTTP.
- Run one test with `go test ./path -run TestName`.
- Report coverage with `go test -cover ./...`.

Test catalog titles match the `t.Run` name or test function name.
