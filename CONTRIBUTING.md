# Contributing to DungeonCore

Welcome, adventurer.

DungeonCore is a multi-agent D\&D platform. We treat the repository like a campaign log: engineering stays disciplined, but the repo keeps a bit of table energy.

## Ground Rules

- Keep changes small, testable, and reviewable.
- Preserve deterministic game state and event flow.
- Never let freeform AI output mutate canonical state directly.
- Prefer schema-first contracts over prose.
- Keep Docker-first development working at all times.
- Do not break local LM Studio support while adding future provider integrations.

## Development Principles

### State is law
Canonical game state lives in the engine and data layer, not in agent narration.

### Communication is bounded
Agent discussion must stay inside explicit budgets and channels.

### Rules are deterministic
Narrative can be flexible; mechanics cannot.

### Visibility is explicit
Agents only see what they are allowed to see.

### Logs matter
Every meaningful transition should be inspectable through events, traces, or structured logs.

## Branch Naming
Use one of these patterns:

```bash
feature/turn-engine
feature/agent-runtime
feature/ui-shell
fix/combat-validation
quest/private-whispers
quest/dm-narration
```

`feature/*` is the safe default. `quest/*` is encouraged if you want the repo to sound like a campaign journal.

## Commit Message Convention
DungeonCore uses conventional commits with lore flavor.

Format:

```bash
<type>: <clear message> — <optional flavor>
```

Examples:

```bash
feat: Roll initiative — implement turn engine
fix: Dispel invalid state mutation in combat
docs: Inscribe the first scrolls of DungeonCore
refactor: Reshape the weave of agent context building
test: Trial of combat resolution
chore: Tend the camp — update Docker images
ci: Forge the pipeline for backend checks
```

### Allowed types

- `feat` — new capability
- `fix` — bug fix
- `docs` — documentation only
- `refactor` — code restructure without behavior change
- `test` — tests only
- `perf` — performance improvement
- `chore` — maintenance or housekeeping
- `ci` — CI/CD changes
- `build` — build system or dependency packaging changes
- `style` — formatting only, no logic changes

### Good commit messages

```bash
feat: Add table-talk message bus — the party finds its voice
fix: Prevent agents from reading private whispers
docs: Describe Redis and RabbitMQ responsibilities
test: Cover invalid action retry flow
```

### Bad commit messages

```bash
stuff
misc changes
feat: moon destiny code magic
```

If the message is funny but nobody can tell what changed, it failed its saving throw.

## Pull Requests
PR titles should stay readable and can optionally use campaign flavor.

Examples:

- `feat: Add DM narration worker`
- `Session 3: Voices in the Dark — agent communication layer`
- `fix: Resolve desync in combat state updates`

### PR checklist

- Describe the change clearly.
- Link related docs/tasks/issues.
- Note any schema or API contract changes.
- Include screenshots or recordings for UI changes.
- Mention Docker, environment, or migration impacts.
- Confirm tests added or explain why not.

## Suggested Workflow

1. Pull latest main.
2. Create a branch.
3. Make one coherent change.
4. Run tests locally.
5. Run lint/format locally.
6. Open a PR with a clear summary.

## Local Development
Expected baseline:

- Docker / Docker Compose
- Python services for AI and orchestration
- React + TSX frontend
- Postgres for durable state
- Redis for cache/pubsub
- RabbitMQ for event-driven workflows
- LM Studio for local LLM inference

When adding any new service, update:

- Docker config
- local dev docs
- environment examples
- service dependency notes

## Architecture Guardrails
Before opening a PR, sanity check these:

- Does this change preserve canonical game state boundaries?
- Does any AI-generated text directly alter state? If yes, stop.
- Are visibility constraints enforced for private messages and hidden world facts?
- Are new actions schema-validated?
- Are side effects observable through logs/events?

## Documentation Expectations
If your change touches architecture, schemas, APIs, or agent behavior, update the relevant markdown docs in `/docs`.

## Testing Expectations
At minimum, add or update tests for:

- schema validation
- state transitions
- event emission
- visibility / access control
- retry / fallback behavior when models misbehave

## Tone
Keep the repo fun, but do not sacrifice clarity. DungeonCore can have lore; it cannot have chaos.
