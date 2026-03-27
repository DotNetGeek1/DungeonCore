# TASKS

## Purpose
This file is the implementation backlog for the custom multi-agent D&D platform. It is written for coding agents such as Codex or Cursor and for human reviewers who want a practical build sequence.

## Delivery Rule
Always prefer a thin, working vertical slice over broad speculative scaffolding. Canonical state, structured actions, and deterministic resolution come before polish.

## Phase 0 — Repository Bootstrap

### T0.1 Create monorepo layout
- Create top-level directories:
  - `apps/web`
  - `services/api-gateway`
  - `services/orchestrator`
  - `services/agent-runtime`
  - `services/game-engine`
  - `services/communication-service`
  - `packages/shared-schemas`
  - `packages/shared-client`
  - `infra/docker`
  - `infra/sql`
- Add root README with startup instructions.
- Add `.editorconfig`, `.gitignore`, and base lint config.

### T0.2 Add Docker Compose stack
- Create `docker-compose.yml`.
- Include services for:
  - postgres
  - redis
  - rabbitmq
  - lmstudio adapter placeholder or config mount
  - api-gateway
  - orchestrator
  - agent-runtime
  - game-engine
  - communication-service
  - web
- Ensure local network and named volumes are configured.
- Add healthchecks where practical.

### T0.3 Environment management
- Add `.env.example` at repo root.
- Define variables for:
  - Postgres DSN
  - Redis URL
  - RabbitMQ URL
  - LM Studio base URL
  - Azure AI Foundry placeholders
  - WebSocket base URL
  - internal service ports
- Add per-service config loader pattern.

## Phase 1 — Shared Contracts First

### T1.1 Create shared schemas package
- Add schema definitions for:
  - `GameState`
  - `CharacterState`
  - `NpcState`
  - `GameEvent`
  - `TableMessage`
  - `PlayerTurn`
  - `AgentContext`
  - `MemoryEntry`
  - API request/response DTOs
- Use JSON-schema-friendly structures.
- Add version field for future migration support.

### T1.2 Define PlayerTurn schema
- Required fields:
  - `thought` optional/private
  - `speech` optional/public
  - `table_talk` optional/public/party
  - `action.type`
  - action payload fields by action subtype
- Add validation rules.
- Add example payloads in docstrings or fixtures.

### T1.3 Define event schema
- Include event types for:
  - session start
  - scene start
  - discussion open/close
  - message created
  - action proposed
  - action validated
  - dice rolled
  - state updated
  - narration emitted
  - turn ended
- Add trace IDs and correlation IDs.

## Phase 2 — Persistence and Infrastructure

### T2.1 Postgres schema
- Add initial SQL migrations for:
  - campaigns
  - sessions
  - scenes
  - actors
  - character_state_snapshots
  - events
  - messages
  - memory_entries
  - action_records
- Add indexes for session timeline queries.

### T2.2 Redis integration
- Add Redis client wrapper.
- Implement:
  - session locks
  - active turn cache
  - discussion window state
  - ephemeral visibility cache

### T2.3 RabbitMQ integration
- Define exchanges and queues for:
  - orchestration events
  - narration jobs
  - memory summarization jobs
  - UI broadcast jobs
- Add basic publisher/consumer abstractions.

## Phase 3 — Backend Services Skeleton

### T3.1 API gateway
- FastAPI app.
- Routes:
  - create session
  - get session state
  - get event history
  - get visible messages
  - operator pause/resume
  - player takeover endpoint placeholder
- WebSocket endpoint for live stream.

### T3.2 Orchestrator service
- Implement state machine with phases:
  - `scene_intro`
  - `discussion`
  - `action_commit`
  - `resolution`
  - `narration`
  - `reaction`
  - `turn_end`
- Add turn runner that calls downstream services.

### T3.3 Game engine service
- Implement deterministic validation for MVP:
  - attack
  - move
  - move_and_attack
  - defend
  - inspect
  - cast_spell_basic
- Add dice roller with seeded option for test runs.

### T3.4 Communication service
- Implement message creation and retrieval.
- Enforce message budgets and visibility.
- Add support for channels:
  - `in_character`
  - `table_talk`
  - `private_whisper`
  - `dm_notice`

### T3.5 Agent runtime service
- Implement provider abstraction.
- Implement context builder.
- Implement memory retrieval.
- Implement schema validation and retry-on-invalid-output.
- Add trace logging.

## Phase 4 — LM Provider Integration

### T4.1 LM Studio adapter
- Implement OpenAI-compatible adapter if available through LM Studio endpoint.
- Configurable model per agent.
- Add healthcheck and timeout handling.
- Add structured output mode or JSON enforcement strategy.

### T4.2 Azure AI Foundry adapter scaffold
- Add provider interface implementation placeholder.
- Do not wire into runtime by default.
- Support provider selection through config.

### T4.3 Model policy config
- Per-agent settings:
  - provider
  - model name
  - temperature
  - max tokens
  - timeout
- Add defaults for DM, player, and narrator variants.

## Phase 5 — Vertical Slice Gameplay

### T5.1 Create MVP scenario fixtures
- One scene.
- Two player agents.
- One combat encounter.
- One simple puzzle or inspectable object.
- Hardcode initial world state fixture.

### T5.2 Discussion window flow
- Active actor can send optional intent.
- Other players can send one reaction each.
- Enforce max messages and max length.
- Close discussion automatically before action commit.

### T5.3 Action lifecycle
- Request structured action from active player.
- Validate in engine.
- Retry once on invalid output.
- Fallback to safe action if still invalid.
- Record full event chain.

### T5.4 Narration lifecycle
- DM receives resolution summary.
- DM emits narration only; no state mutation allowed.
- Broadcast narration through event stream.

## Phase 6 — Frontend MVP

### T6.1 React application shell
- Create routes or single-page layout for:
  - spectator view
  - director view
  - human player view placeholder

### T6.2 Live session screen
- Panels:
  - main transcript
  - tactical chat
  - private messages area
  - current turn info
  - state sidebar
  - event/debug panel

### T6.3 WebSocket integration
- Subscribe to session events.
- Render incremental updates.
- Handle reconnect gracefully.

### T6.4 Operator controls
- Buttons for:
  - pause
  - resume
  - next step in dev mode
  - inject test event
  - take over character placeholder

## Phase 7 — Quality Gates

### T7.1 Unit tests
- Schema validation tests.
- Rules engine tests.
- message visibility tests.
- memory retrieval tests.

### T7.2 Integration tests
- Start a session.
- Run one full turn.
- Assert event order.
- Assert state patch correctness.
- Assert UI stream payload shape.

### T7.3 Chaos tests
- malformed agent JSON
- LM Studio timeout
- duplicate event publish
- invalid action proposal
- missing discussion close event

## Phase 8 — Human-in-the-Loop

### T8.1 Character takeover
- Allow a human to replace one player agent for a turn or session.
- Preserve same action schema and message channels.

### T8.2 Director overrides
- Replace agent proposal before resolution.
- Edit world state in development mode.
- Re-run narration from a chosen resolution payload.

## Phase 9 — Observability

### T9.1 Trace logging
- Log per turn:
  - context summary
  - selected memories
  - outbound prompt envelope metadata
  - raw model response
  - parsed output
  - validation result
- Never treat logs as canonical game state.

### T9.2 Session replay
- Rebuild UI from event log.
- Add simple playback mode.

## Definition of Done for MVP
- One Docker Compose command starts all required services.
- One sample session can run end-to-end.
- Two player agents can discuss, act, and complete a turn.
- Game state remains canonical outside the LLM.
- UI shows transcript, tactical chat, and state updates live.
- Logs and events are sufficient to debug a broken turn without guesswork.
