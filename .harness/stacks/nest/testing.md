# Stack Testing — NestJS

Commands come from `.harness/config.json` and run in `src/`.

- Unit specs live beside the source as `*.spec.ts`. E2E tests live in `src/test/`.
- Run one file with `npx jest <path/to/file.spec.ts>`.
- Report coverage with `npm run test:cov`.
- Unit tests do no real I/O. Mock configuration, HTTP clients, global `fetch` and
  any external SDK.

| Unit under test | Setup |
|---|---|
| Pure provider (dependencies are constructor arguments) | `new Service(fakeDep)`, no `TestingModule` |
| Needs the Nest DI graph, guards or pipes | `Test.createTestingModule().overrideProvider()` |
| Controller | Instantiate with a mocked service; assert delegation, status and mapping |
| Guard or interceptor | Hand-build a fake `ExecutionContext`; mock `Reflector` |
| DTO | `plainToInstance` + `validate`; assert constraint keys |

Test catalog titles match `it(...)` titles verbatim.
