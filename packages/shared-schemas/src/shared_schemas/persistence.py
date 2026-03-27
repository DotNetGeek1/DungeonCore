from __future__ import annotations

from datetime import datetime

from pydantic import Field

from .actions import ActionUnion
from .base import EntityId, NonEmptyString, SchemaVersionedModel
from .state import GameState


class EventHistoryQuery(SchemaVersionedModel):
    session_id: EntityId
    limit: int = Field(default=50, ge=1, le=500)
    event_type: NonEmptyString | None = None
    actor_id: EntityId | None = None


class StateSnapshotRecord(SchemaVersionedModel):
    id: EntityId
    session_id: EntityId
    scene_id: EntityId
    turn_number: int = Field(ge=0)
    active_actor_id: EntityId | None = None
    state: GameState
    created_at: datetime


class ActionRecord(SchemaVersionedModel):
    id: EntityId
    session_id: EntityId
    actor_id: EntityId
    turn_number: int = Field(ge=0)
    action_type: NonEmptyString
    status: NonEmptyString
    source: NonEmptyString
    event_id: EntityId | None = None
    normalized_action: ActionUnion | None = None
    created_at: datetime
