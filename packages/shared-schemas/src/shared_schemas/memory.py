from __future__ import annotations

from pydantic import Field

from .base import EntityId, NonEmptyString, SchemaVersionedModel
from .enums import MemoryType, Visibility


class MemoryEntry(SchemaVersionedModel):
    id: EntityId
    session_id: EntityId
    actor_id: EntityId
    memory_type: MemoryType
    text: NonEmptyString
    importance: int = Field(ge=1, le=10)
    tags: list[NonEmptyString] = Field(default_factory=list)
    created_at_turn: int = Field(ge=0)
    source_event_id: EntityId | None = None
    visibility: Visibility
