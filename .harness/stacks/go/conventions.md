# Stack Conventions — Go

The application root is `src/`, which holds `go.mod`.

- Format with `gofmt`; `go vet ./...` must be clean.
- Package names are short, lowercase and singular.
- Return errors; do not panic for expected failures. Wrap with
  `fmt.Errorf("context: %w", err)`.
- Accept interfaces and return concrete types.
- Pass `context.Context` as the first argument of I/O functions.
