# Stack Conventions — Java

The application root is `src/`, which holds `pom.xml`. Sources are therefore in
`src/src/main/java/` and tests in `src/src/test/java/`. This is the normal Maven
layout one level down; do not flatten it.

- Packages are lowercase under the project group id.
- Classes are PascalCase; methods and fields are camelCase.
- Inject collaborators through constructors.
- Use unchecked domain exceptions with meaningful names; never swallow exceptions.
- Prefer records and final fields for immutable values.
