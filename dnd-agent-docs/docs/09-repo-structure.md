# Suggested Repository Structure

## Monorepo Layout

```text
repo/
├─ apps/
│  ├─ api/
│  │  ├─ app/
│  │  ├─ tests/
│  │  └─ Dockerfile
│  ├─ orchestrator/
│  │  ├─ app/
│  │  ├─ tests/
│  │  └─ Dockerfile
│  ├─ agent-runtime/
│  │  ├─ app/
│  │  ├─ tests/
│  │  └─ Dockerfile
│  ├─ game-engine/
│  │  ├─ app/
│  │  ├─ tests/
│  │  └─ Dockerfile
│  ├─ communication-service/
│  │  ├─ app/
│  │  ├─ tests/
│  │  └─ Dockerfile
│  └─ web/
│     ├─ src/
│     ├─ public/
│     └─ Dockerfile
├─ packages/
│  ├─ shared-schemas/
│  ├─ shared-events/
│  ├─ shared-config/
│  └─ campaign-content/
├─ infra/
│  ├─ docker/
│  ├─ compose/
│  ├─ migrations/
│  └─ env/
├─ docs/
├─ scripts/
├─ .env.example
├─ docker-compose.yml
└─ Makefile
```

## Notes on This Structure

### apps/
Holds deployable services.

### packages/
Holds shared contracts and non-deployable code.

### infra/
Holds infrastructure setup and migrations.

### docs/
Holds design documents like the ones in this package.

## Service Boundaries

### api
Public-facing HTTP and WebSocket entrypoint.

### orchestrator
Owns the runtime state machine.

### agent-runtime
Owns model calls, memory retrieval, and response validation.

### game-engine
Owns deterministic rules and state patch production.

### communication-service
Owns message persistence, visibility logic, and communication windows.

### web
Owns spectator/director/player interfaces.

## Shared Packages

### shared-schemas
Pydantic or JSON Schema contracts shared across services.

### shared-events
Event type definitions and serialization helpers.

### shared-config
Environment parsing and configuration models.

### campaign-content
Static quest definitions, NPC templates, maps, and starter data.

## Docker Guidance

Keep one Dockerfile per app service.
Use Compose profiles if desired for optional local tooling.

Recommended local infra in Compose:
- postgres
- redis
- rabbitmq
- lmstudio bridge if needed
- optional admin tools

## Build Hygiene

- pin dependencies
- centralize config parsing
- version schemas carefully
- keep service boundaries boring and explicit

Boring architecture is underrated. It leaves more room for the goblins to be weird.
