# System Architecture

## Technology Stack

### Backend
- Python services
- FastAPI for HTTP + WebSocket APIs
- Pydantic for schemas and validation

### Frontend
- React + TypeScript (TSX)
- Vite or Next.js depending on deployment preference
- WebSocket client for live updates

### Infrastructure
- Docker for all services
- Postgres for canonical state and durable records
- Redis for cache, ephemeral state, locks, and light pub/sub
- RabbitMQ for queued jobs and event fan-out

### Model Access
- LM Studio for local model serving in development and early runtime
- Azure AI Foundry as a future provider for hosted models and enterprise-scale deployment

## High-Level Container View

```text
+-----------------------+
| React Frontend        |
| - Spectator UI        |
| - Director UI         |
| - Human Player UI     |
+-----------+-----------+
            |
            v
+-----------------------+
| API Gateway           |
| - REST                |
| - WebSockets          |
| - Auth later          |
+-----------+-----------+
            |
            v
+-----------------------+
| Orchestrator Service  |
| - Turn state machine  |
| - Discussion windows  |
| - Action lifecycle    |
+---+-----------+---+---+
    |           |   |
    v           v   v
+-------+   +------+  +----------------+
| Agent |   | Game |  | Communication  |
| Runtime|  |Engine|  | Service        |
+-------+   +------+  +----------------+
    |           |            |
    +-----+-----+------------+
          |
          v
+---------------------------------------+
| Shared Infra                          |
| Postgres | Redis | RabbitMQ | LM Studio |
+---------------------------------------+
```

## Service Responsibilities

### API Gateway
Responsible for client-facing APIs.

Functions:
- session start/stop commands
- read-only state fetches
- event stream subscription
- operator actions such as pause, resume, override, takeover

### Orchestrator Service
Responsible for the game loop and lifecycle control.

Functions:
- determine active phase
- open/close discussion windows
- request agent outputs
- trigger validation and resolution
- emit state transition events
- handle retries, timeouts, and fallbacks

### Agent Runtime Service
Responsible for invoking LLM-backed agents with filtered context.

Functions:
- construct agent context
- retrieve relevant memories
- call model adapters
- validate structured outputs
- log traces

### Game Engine Service
Responsible for deterministic game logic.

Functions:
- action validation
- movement and range checks
- dice rolling
- combat resolution
- state patch generation

### Communication Service
Responsible for table messages and whisper visibility.

Functions:
- store messages
- enforce message budgets
- apply visibility rules
- expose messages to eligible recipients
- summarize recent communication for context building

## Why RabbitMQ, Redis, and Postgres all exist here

### Postgres
Use Postgres for durable state and auditability.

Store:
- campaigns
- scenes
- actors
- event log
- messages
- memory entries
- action records
- session metadata

### Redis
Use Redis for fast-changing coordination concerns.

Store:
- ephemeral turn locks
- active session cache
- recently accessed context bundles
- transient rate limits
- in-flight operator controls

### RabbitMQ
Use RabbitMQ when one action fans out into multiple asynchronous tasks.

Examples:
- publish event updates to subscribers
- queue narration generation
- queue memory summarization
- queue analytics hooks
- queue provider-specific model requests later if needed

## Deployment Model

### Local Development
Use Docker Compose.

Recommended services:
- frontend
- api
- orchestrator
- agent-runtime
- game-engine
- communication-service
- postgres
- redis
- rabbitmq
- optional observability stack

### Later Environments
Possible progression:
- single-node Docker host
- Kubernetes if concurrency, tenancy, or observability demands grow

Do not start with Kubernetes unless the team enjoys pain as a hobby.

## Architectural Boundaries

### LLMs do not own truth
They generate proposals, narration, and reasoning artifacts. They do not own game state.

### The engine does not write flavor
It validates and resolves mechanics. It does not improvise story text.

### The frontend does not infer game rules
It renders whatever canonical state and event streams provide.

### Providers are swappable
The model adapter boundary should make LM Studio and Azure AI Foundry look interchangeable from the rest of the runtime.
