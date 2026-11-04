# Stack Conventions — NestJS

The application root is `src/`. Commands run from there, so the Nest source
directory is `src/src/`. This is the normal Nest layout one level down; do not
flatten it.

- One Nest module per domain concept, under `src/src/<module>/`.
- Controllers delegate to services and hold no business logic.
- Providers receive collaborators through constructor injection.
- DTOs validate input at the boundary with `class-validator`.
- Files use kebab-case with a role suffix: `user.service.ts`,
  `user.controller.ts`, `create-user.dto.ts`.
- Do not disable TypeScript checks to make the build pass.
