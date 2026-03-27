# Game Engine

## Purpose

The game engine owns canonical rules execution and state transition generation.

The engine should be deterministic wherever practical. It exists to stop narrative drift from corrupting mechanics.

## Canonical State

Canonical state must live outside the LLMs.

Recommended top-level state buckets:
- campaign metadata
- scene metadata
- turn metadata
- party state
- NPC and enemy state
- map or abstract location state
- quest/objective state
- inventory/resources
- visibility and hidden fact references

## Suggested State Skeleton

```python
from pydantic import BaseModel
from typing import Dict, List, Optional, Any

class CharacterState(BaseModel):
    actor_id: str
    name: str
    hp: int
    max_hp: int
    ac: int
    position: Optional[str] = None
    status_effects: List[str] = []
    inventory: List[str] = []
    spell_slots: Dict[str, int] = {}

class SceneState(BaseModel):
    scene_id: str
    name: str
    summary: str
    turn_number: int
    active_actor_id: str
    phase: str

class GameState(BaseModel):
    campaign_id: str
    scene: SceneState
    characters: Dict[str, CharacterState]
    npcs: Dict[str, CharacterState]
    quests: List[Dict[str, Any]] = []
    flags: Dict[str, Any] = {}
```

## Event-First Model

Every meaningful step should emit an event.

Recommended event categories:
- session lifecycle
- scene lifecycle
- communication events
- action proposal events
- validation events
- dice and resolution events
- state patch events
- narration events
- operator intervention events

## Why Event-First Matters

Benefits:
- replayability
- debugging
- auditing
- deterministic reconstruction
- analytics
- easy UI streaming

## Turn State Machine

Recommended phases:
- `scene_intro`
- `discussion`
- `action_selection`
- `action_resolution`
- `narration`
- `reaction`
- `turn_advance`

A turn should move through these phases with explicit transitions.

## Example Turn Flow

1. set active actor
2. open discussion window
3. collect bounded messages
4. request action from active actor
5. validate action
6. resolve mechanics
7. apply state patch
8. request DM narration
9. emit events to UI
10. advance turn

## Rules Scope for v1

Implement a D&D-inspired subset first.

Suggested mechanics:
- initiative order
- movement budget
- attack roll
- damage roll
- basic spell usage
- skill checks
- inventory usage
- line-of-sight or a simplified equivalent
- basic conditions like prone, stunned, poisoned if useful

Avoid full rules completeness early. Grapple edge cases can wait for the sequel nobody asked for yet.

## Validation Responsibilities

The engine validates:
- whether the actor can legally act now
- whether targets exist and are visible if required
- whether movement is legal
- whether required resources exist
- whether the proposed action matches phase constraints

## Resolution Responsibilities

The engine resolves:
- dice rolls
- hit/miss
- damage application
- condition application/removal
- resource expenditure
- triggered events
- end-of-turn effects

## Narration Boundary

The engine should return structured results. The DM agent then turns those results into prose.

Example engine output:

```json
{
  "resolution_type": "attack",
  "attacker": "fighter_01",
  "target": "goblin_shaman",
  "attack_roll": 18,
  "hit": true,
  "damage": 7,
  "target_hp_after": 5
}
```

## Determinism and Seeds

Where randomness exists, record:
- die type
- seed if applicable
- rolled value
- modifier
- total

This supports exact replay and testing.

## Persistence Pattern

Recommended write pattern:
1. validate action request
2. emit proposal event
3. resolve mechanics
4. emit resolution events
5. write resulting state patch to Postgres
6. publish stream updates

Do not let the frontend infer state from text output. Text lies. State tables should not.
