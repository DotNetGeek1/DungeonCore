from __future__ import annotations

from pydantic import Field

from .base import EntityId, NonEmptyString, TimestampedModel
from .enums import MessageChannel, ScenePhase, Visibility


class TableMessage(TimestampedModel):
    id: EntityId
    session_id: EntityId
    scene_id: EntityId
    turn_number: int = Field(ge=0)
    phase: ScenePhase
    channel: MessageChannel
    sender_id: EntityId
    recipient_ids: list[EntityId] = Field(default_factory=list)
    visibility: Visibility
    text: NonEmptyString
