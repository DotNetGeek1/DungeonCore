# Open Questions and Decisions to Lock Down

## Rules Fidelity

How close should v1 be to actual D&D 5e?

Recommendation:
Start with a D&D-inspired subset and document deviations clearly.

## Spatial Model

Will the system use:
- grid coordinates
- zone-based rooms
- abstract range bands

Recommendation:
Use a simplified grid or zone model first.

## NPC Control Strategy

Should every NPC be agent-driven, or only important ones?

Recommendation:
Only important NPCs need agent-style behavior early. Most can use deterministic or lightweight scripted policies.

## Message Budget Policy

How many messages can agents send per phase?

Recommendation:
Keep it small for v1.
Example:
- active actor: 1 intent + 1 follow-up
- each other party member: 1 response
- reaction phase: 1 short message if relevant

## Memory Summarization Timing

When should memory consolidation run?

Recommendation:
After scene transitions or every N turns, asynchronously via RabbitMQ.

## Model Assignment Strategy

Will all agents use the same model?

Recommendation:
No. Support per-agent model assignment from the beginning.

## Operator Scope

How much god mode should director tools have?

Recommendation:
Full control in development. More guardrails later if exposing to others.

## Persistence Depth

Will the system persist raw prompts and raw outputs?

Recommendation:
Persist enough for debugging, but separate raw LLM traces from canonical game records.

## Authentication and Multi-User Support

Is this initially a private dev tool or a multi-user platform?

Recommendation:
Treat v1 as a trusted internal tool. Add auth when real sharing becomes necessary.

## Observability Stack

Will you add OpenTelemetry, Grafana, or similar early?

Recommendation:
At minimum, structure logs and trace IDs from day one. Add full observability once the runtime loop is stable.

## Final Recommendation

Before asking Codex or Cursor to scaffold aggressively, lock down these three artifacts first:
- the turn state machine
- the action schema
- the communication schema

Those three pieces are the spine of the project. Get them right, and the rest stops fighting you.
