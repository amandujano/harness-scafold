# Stack Conventions — Python

The application root is `src/`, which holds `pyproject.toml`.

- Follow PEP 8; modules and functions are snake_case, classes PascalCase.
- Add type hints to public functions.
- Raise named exceptions; do not return `None` to signal failure.
- Keep the package in `src/app/`; rename it when the project has a better name.
