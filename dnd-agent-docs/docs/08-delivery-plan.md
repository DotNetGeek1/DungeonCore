# Delivery Plan

## Philosophy

Build the narrowest thing that proves the architecture.

Do not start with full campaigns, full 5e parity, or polished visuals. Start with one stable loop.

## Phase 0: Project Skeleton

Deliverables:
- Docker Compose setup
- Python service skeletons
- React frontend skeleton
- Postgres/Redis/RabbitMQ wiring
- environment configuration for LM Studio

Exit criteria:
- all containers boot
- frontend can call backend
- backend can persist to Postgres
- backend can reach LM Studio

## Phase 1: Minimal Runtime Loop

Deliverables:
- single scene
- one DM agent
- one player agent
- deterministic turn progression
- event logging
- transcript rendering

Exit criteria:
- a complete simple encounter can run end-to-end
- all state transitions are persisted

## Phase 2: Structured Action Contracts

Deliverables:
- action schema
- output validator
- invalid response retry path
- deterministic resolution engine

Exit criteria:
- malformed model output does not crash the session
- action execution is auditable and repeatable

## Phase 3: Communication Layer

Deliverables:
- table messages
- visibility rules
- discussion windows
- bounded message budgets

Exit criteria:
- agents can coordinate before acting
- private whispers remain private
- chatter does not loop forever

## Phase 4: Multi-Agent Party

Deliverables:
- multiple player agents
- turn order support
- broader scene context
- shared and private memory basics

Exit criteria:
- a small party can complete a short quest
- the system remains stable over many turns

## Phase 5: Director and Human Control

Deliverables:
- pause/resume
- take over character
- override action
- inspect private memory/context

Exit criteria:
- a human can join and leave cleanly
- operator actions are logged as events

## Phase 6: Hardening

Deliverables:
- replay support
- test harnesses
- chaos handling
- improved summaries and memory pruning
- provider abstraction ready for Azure AI Foundry

Exit criteria:
- sessions are replayable
- failure cases are recoverable
- the platform is ready for larger experiments

## Testing Strategy

### Unit Tests
- action validation
- movement legality
- message visibility
- memory retrieval filters
- schema validation

### Integration Tests
- full turn flow
- event persistence
- WebSocket updates
- model invocation contract

### Chaos Tests
- invalid JSON
- empty provider response
- late response timeout
- repeated message loops
- duplicate event publication
- operator override mid-turn

## Engineering Priorities

Order of importance:
1. correctness of state transitions
2. observability
3. bounded communication
4. human override capability
5. narrative quality

Good prose with broken state is still broken. It just fails poetically.
