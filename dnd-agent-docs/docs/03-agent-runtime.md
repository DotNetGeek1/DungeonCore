# Agent Runtime

## Goal

Build a custom agent runtime that is simple, testable, and explicit.

An agent is not magic. It is a controlled composition of:
- identity and policy
- visible context
- retrieved memory
- model invocation
- structured output validation
- post-processing hooks

## Agent Types

### DM Agent
Responsibilities:
- narrate outcomes
- frame scenes
- determine NPC intent
- manage pacing and consequence flavor

Should not:
- directly mutate canonical state
- silently alter rules outcomes
- bypass hidden information policies

### Player Agent
Responsibilities:
- interpret visible world state
- coordinate with other agents
- choose one valid action per turn
- act according to class, goals, and personality

Should not:
- narrate outcomes as fact
- invent hidden state
- decide its own dice results

### NPC Agent (optional early, fuller later)
Responsibilities:
- produce behavior proposals for non-player actors
- support more lifelike interactions where worthwhile

## Recommended Agent Definition

```python
from pydantic import BaseModel
from typing import List, Literal, Dict, Any

class AgentConfig(BaseModel):
    id: str
    role: Literal["dm", "player", "npc"]
    name: str
    system_prompt: str
    goals: List[str]
    model_provider: str
    model_name: str
    temperature: float = 0.4
    tools: List[str] = []
    output_schema_name: str
```

## Runtime Pipeline

1. receive invocation request
2. build filtered context for the target agent
3. retrieve relevant memory slices
4. assemble prompt package
5. invoke model provider through adapter
6. parse and validate response
7. retry or fallback if invalid
8. persist trace metadata
9. return structured output to orchestrator

## Context Model

Each agent sees a tailored context, not the whole world dump.

Recommended sections:
- identity and goals
- current scene summary
- visible entities and positions
- recent visible events
- recent visible messages
- relevant memory recall
- available actions or communication budget
- explicit output contract

## Memory Layers

### Working Memory
Recent turn-local details.

Examples:
- last few messages
- most recent narration
- latest tactical warnings

### Episodic Memory
Specific past events likely to matter again.

Examples:
- suspicious priest lied in chapel
- goblin shaman resisted radiant damage

### Semantic Memory
Stable beliefs, preferences, and relationships.

Examples:
- prefers protecting allies over risky offense
- distrusts noble NPCs

### Private Memory
Only visible to that agent and possibly operator tools.

Examples:
- secretly wants the relic
- suspects another player is hiding something

## Memory Retrieval Strategy

Do not shovel the entire campaign transcript into every model call.

Retrieve by:
- recency
- semantic relevance to current scene
- importance score
- source visibility

## Communication vs Action Outputs

Agent output should separate thought, speech, and action.

Recommended structure:

```json
{
  "private_thought": "The shaman is the main threat.",
  "table_talk": "Focus the shaman first.",
  "in_character_speech": "Steel yourselves. I strike now.",
  "action": {
    "type": "attack",
    "target": "goblin_shaman",
    "movement": ["B4", "B5"]
  }
}
```

## Guardrails

### Validation
- response must parse
- response must match the expected schema
- action must be legal for current phase
- messages must fit budget and visibility rules

### Retry Policy
Retry once or twice on:
- malformed JSON
- missing required fields
- obviously impossible references

Do not create endless self-healing loops. That road leads to sadness.

### Fallback Policy
If the agent still fails:
- choose a safe default action
- mark the event as a fallback
- continue the session

## Provider Adapter Interface

The rest of the system should not care whether the provider is LM Studio or Azure AI Foundry.

Recommended adapter surface:

```python
class ModelRequest(BaseModel):
    system_prompt: str
    user_prompt: str
    temperature: float = 0.4
    response_format: Dict[str, Any] | None = None

class ModelResponse(BaseModel):
    raw_text: str
    latency_ms: int
    provider: str
    model: str

class ModelAdapter:
    async def generate(self, request: ModelRequest) -> ModelResponse:
        raise NotImplementedError
```

## Tracing

Every invocation should log:
- agent id
- provider/model
- prompt hash
- visible context summary hash
- selected memories
- validation result
- retries
- latency

This is mandatory if you want to debug why the bard decided to negotiate with the wall.
