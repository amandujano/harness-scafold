# {{project}}

Application code lives in `src/` (stack: {{stack}}). Everything about the AI
development process lives in `.harness/`, and Claude Code's own configuration in
`.claude/`.

## Working on this project

1. Open Claude Code at the project root.
2. Describe what you want. The leader turns it into features in
   `.harness/state/feature_list.json`.
3. Ask at any time what comes next:

   ```bash
   .harness/bin/harness next
   ```

4. When a spec is ready, read `.harness/specs/<feature>/` and approve it from
   your own terminal:

   ```bash
   .harness/bin/harness approve <feature>
   ```

5. Validate the project state and run the tests:

   ```bash
   .harness/bin/harness check
   ```

The process is described in `.harness/AGENTS.md`. The rules are in
`.harness/rules.json`, and project commands in `.harness/config.json`.
