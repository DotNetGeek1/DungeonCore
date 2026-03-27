# Data Models and Schemas

## Purpose

This document defines baseline shapes for key runtime entities.

These are not final. They are intended to give implementation agents enough structure to scaffold the system cleanly.

## Game State

```python
from pydantic import BaseModel
from typing import List, Dict, Literal, Optional, Any

class Position(BaseModel):
    node_id: str

class CharacterState(BaseModel):
    actor_id: str
    name: str
    role: Literal["player", "npc", "enemy"]
    hp: int
    max_hp: int
    ac: int
    initiative: int = 0
    position: Optional[Position] = None
    status_effects: List[str] = []
    inventory: List[str] = []
    spell_slots: Dict[str, int] = {}
    alive: bool = True

class SceneState(BaseModel):
    scene_id: str
    name: str
    summary: str
    phase: str
    turn_number: int
    active_actor_id: str

class GameState(BaseModel):
    campaign_id: str
    scene: SceneState
    characters: Dict[str, CharacterState]
    quests: List[Dict[str, Any]] = []
    flags: Dict[str, Any] = {}
```

## Table Message

```python
class TableMessage(BaseModel):
    id: str
    turn_number: int
    phase: Literal["discussion", "reaction", "narration"]
    channel: Literal["in_character", "table_talk", "private_whisper", "dm_notice"]
    sender_id: str
    recipient_ids: List[str] | Literal["all"]
    visibility: Literal["public", "party", "private", "dm_only"]
    text: str
    created_at: str
```

## Memory Entry

```python
class MemoryEntry(BaseModel):
    id: str
    actor_id: str
    memory_type: Literal["observation", "belief", "goal", "relationship", "summary"]
    text: str
    importance: int
    tags: List[str] = []
    created_at_turn: int
    visibility: Literal["private", "shared", "dm_only"]
```

## Player Turn Output

```python
class ActionPayload(BaseModel):
    type: str
    target_id: Optional[str] = None
    movement_path: List[str] = []
    item_id: Optional[str] = None
    spell_id: Optional[str] = None
    extra: Dict[str, Any] = {}

class PlayerTurnOutput(BaseModel):
    private_thought: str
    table_talk: Optional[str] = None
    in_character_speech: Optional[str] = None
    action: ActionPayload
```

## Action Validation Result

```python
class ActionValidationResult(BaseModel):
    valid: bool
    errors: List[str] = []
    normalized_action: Optional[ActionPayload] = None
```

## Resolution Result

```python
class ResolutionResult(BaseModel):
    resolution_type: str
    actor_id: str
    target_id: Optional[str] = None
    dice: List[Dict[str, Any]] = []
    effects: List[Dict[str, Any]] = []
    state_patch: Dict[str, Any] = {}
```

## Event Record

```python
class GameEvent(BaseModel):
    id: str
    session_id: str
    turn_number: int
    event_type: str
    payload: Dict[str, Any]
    created_at: str
```

## Operator Command

```python
class OperatorCommand(BaseModel):
    command_type: Literal[
        "pause", "resume", "override_action", "inject_event", "edit_state", "takeover", "release_takeover"
    ]
    actor_id: Optional[str] = None
    payload: Dict[str, Any] = {}
```

## Schema Notes

### Keep schemas explicit
Do not rely on fuzzy dicts everywhere. That becomes a debugging tax with interest.

### Version contracts
Once the UI and services are talking, version payloads where breakage risk exists.

### Store raw and normalized forms when helpful
For example, keep raw model output for debugging, but do not let it leak into canonical state handling.
