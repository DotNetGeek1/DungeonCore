# UI and API Design

## Frontend Goals

The frontend should make the session legible, inspectable, and controllable.

It must support:
- real-time observation
- human participation
- operator intervention
- state inspection
- event replay later

## Primary UI Modes

### Spectator UI
Displays:
- DM narration
- in-character speech
- table talk
- state summary
- actor cards
- turn order
- dice outcomes

### Director UI
Adds:
- pause/resume
- approve/reject action
- inspect agent context
- inspect private memory
- edit state in dev mode
- inject test event
- switch a character to human control

### Human Player UI
Adds:
- submit tactical messages
- speak in character
- whisper privately
- choose a structured action
- see only allowed private information

## Suggested Layout

### Main Areas
- transcript panel
- tactical chat panel
- private messages panel
- map or scene panel
- actor status panel
- turn timeline / event feed
- operator tools drawer

## UI Streams

The UI should subscribe to a WebSocket stream of session events.

Recommended event groups:
- `session.updated`
- `phase.changed`
- `message.created`
- `action.proposed`
- `action.validated`
- `dice.rolled`
- `state.updated`
- `narration.created`
- `operator.intervened`

## REST API Responsibilities

Use REST for:
- initial session load
- historical event retrieval
- actor sheet retrieval
- campaign setup actions
- operator commands that are not latency-sensitive

Use WebSockets for:
- live state changes
- discussion messages
- narration stream
- dice results
- control updates

## Suggested API Surface

### Session APIs
- `POST /sessions`
- `GET /sessions/{id}`
- `POST /sessions/{id}/start`
- `POST /sessions/{id}/pause`
- `POST /sessions/{id}/resume`
- `POST /sessions/{id}/stop`

### State APIs
- `GET /sessions/{id}/state`
- `GET /sessions/{id}/events`
- `GET /sessions/{id}/actors`
- `GET /sessions/{id}/messages`

### Control APIs
- `POST /sessions/{id}/override-action`
- `POST /sessions/{id}/takeover`
- `POST /sessions/{id}/release-takeover`
- `POST /sessions/{id}/inject-event`

### Communication APIs
- `POST /sessions/{id}/messages`

### Human Action APIs
- `POST /sessions/{id}/actions`

## Frontend State Management

Recommended approach:
- use React Query or equivalent for REST hydration
- keep live session state synchronized via WebSockets
- normalize event stream objects into client stores

## UI Contracts

Avoid deriving game truth from rendered prose.

The frontend should render from:
- canonical state payloads
- event payloads
- typed message objects
- structured action records

## Accessibility and Debuggability

Requirements:
- clear distinction between table talk and in-world dialogue
- visibility markers for private information
- obvious phase indicator
- action status labels: proposed, validated, resolved, overridden
- easy copy/export of event logs for debugging
