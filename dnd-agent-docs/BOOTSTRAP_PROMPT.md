# BOOTSTRAP PROMPT FOR CODEX / CURSOR

Use this prompt as the starting instruction for a coding agent. It is written to reduce drift, avoid over-engineering, and force a working vertical slice.

---

You are scaffolding a custom multi-agent D&D platform from the Markdown docs in this repository.

## Primary Goal
Build a minimal but real end-to-end vertical slice for a custom multi-agent D&D runtime.

The system must support:
- a DM agent
- at least two player agents
- bounded table communication
- structured action submission
- deterministic action validation and resolution
- canonical game state outside the LLM
- a React frontend that can watch the session live

## Non-Negotiable Architectural Rules
1. Canonical game state lives in code and storage, not in model outputs.
2. LLMs may propose actions and narration, but may not directly mutate game state.
3. Rules resolution must be deterministic code for the MVP.
4. All state-changing steps must emit structured events.
5. Agent-to-agent communication is first-class but bounded by budgets and visibility rules.
6. The first deliverable is a working vertical slice, not a complete D&D ruleset.

## Technology Constraints
- Backend services: Python
- Frontend: React + TypeScript
- Infra: Docker Compose
- Datastores: Postgres, Redis, RabbitMQ
- Local LLM access: LM Studio
- Future hosted provider support: Azure AI Foundry abstraction only, not fully wired

## Required Repository Structure
Create or align to:
- `apps/web`
- `services/api-gateway`
- `services/orchestrator`
- `services/agent-runtime`
- `services/game-engine`
- `services/communication-service`
- `packages/shared-schemas`
- `packages/shared-client`
- `infra/sql`
- `infra/docker`

## Implementation Order
Follow this order exactly unless a dependency forces a small deviation.

### Step 1
Create the monorepo skeleton and Docker Compose stack.

### Step 2
Create shared schemas first:
- `GameState`
- `GameEvent`
- `TableMessage`
- `PlayerTurn`
- API DTOs

### Step 3
Implement backend service shells with health endpoints and internal client stubs.

### Step 4
Implement the orchestrator turn state machine with these phases:
- scene_intro
- discussion
- action_commit
- resolution
- narration
- reaction
- turn_end

### Step 5
Implement deterministic game-engine validation and resolution for a very small action subset:
- move
- attack
- move_and_attack
- defend
- inspect

### Step 6
Implement communication service support for channels:
- in_character
- table_talk
- private_whisper
- dm_notice

### Step 7
Implement agent runtime with:
- provider abstraction
- LM Studio adapter
- context builder
- memory retrieval stub
- structured output validation
- one retry on invalid action

### Step 8
Implement one sample scenario fixture and one runnable end-to-end session.

### Step 9
Implement React spectator UI with:
- transcript panel
- tactical chat panel
- state panel
- current turn panel
- live WebSocket updates

## Output Quality Rules
- Prefer simple, explicit code over clever abstractions.
- Do not introduce Kubernetes, microservice mesh tooling, or heavy workflow frameworks.
- Do not implement full 5e rules.
- Do not merge narrative text with game-state mutations.
- Do not use freeform strings where typed schemas are practical.
- Do not leave TODO-only shells for the core turn loop.

## MVP Scope
The MVP is complete when:
- Docker Compose starts the full stack.
- A sample session can run.
- The DM and two player agents can exchange bounded messages.
- The active player can submit a structured action.
- The game engine validates and resolves the action.
- The DM narrates the result.
- The frontend shows the live flow.

## Coding Expectations
- Use clear naming.
- Keep modules small and focused.
- Include docstrings or README snippets where the system boundaries matter.
- Add tests for schemas and the game engine.
- Add one integration test for a single full turn.

## When Tradeoffs Appear
Choose in this order:
1. correctness of canonical state
2. event auditability
3. schema clarity
4. vertical-slice completeness
5. developer ergonomics
6. future extensibility

## What To Build First In Practice
Start by generating:
1. `docker-compose.yml`
2. root `.env.example`
3. shared schema package
4. Python service skeletons with FastAPI
5. minimal React app shell
6. sample scenario fixture
7. one end-to-end turn execution path

## Final Instruction
Do not stop at repo scaffolding. Produce a runnable minimal implementation for the vertical slice. If a choice is unclear, choose the simplest architecture that preserves the non-negotiable rules above.

---

## Suggested Follow-up Prompt
After the initial scaffold is complete, use this follow-up instruction:

"Now implement the first runnable vertical slice. Add the sample scenario, wire the services together, run one full turn through discussion, action, resolution, and narration, and expose the result in the React UI."
