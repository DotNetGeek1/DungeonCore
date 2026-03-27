from __future__ import annotations

from typing import Literal

from pydantic import Field

from .actions import ActionUnion, PlayerTurn
from .base import EntityId, NonEmptyString, SchemaVersionedModel
from .enums import ActionSubmissionSource, ControllerType, OperatorCommandType, SessionStatus
from .events import GameEvent
from .messages import TableMessage
from .persistence import EventHistoryQuery
from .state import GameState


class CreateSessionRequest(SchemaVersionedModel):
    campaign_id: EntityId
    scene_id: EntityId
    player_character_ids: list[EntityId] = Field(default_factory=list)
    npc_ids: list[EntityId] = Field(default_factory=list)
    seed: int | None = None


class SessionSummary(SchemaVersionedModel):
    session_id: EntityId
    campaign_id: EntityId
    scene_id: EntityId
    status: SessionStatus


class CreateSessionResponse(SchemaVersionedModel):
    session: SessionSummary
    state: GameState


class GetSessionStateResponse(SchemaVersionedModel):
    session_id: EntityId
    state: GameState


class GetEventHistoryResponse(SchemaVersionedModel):
    session_id: EntityId
    events: list[GameEvent] = Field(default_factory=list)
    next_cursor: str | None = None


class GetEventHistoryRequest(EventHistoryQuery):
    pass


class GetVisibleMessagesResponse(SchemaVersionedModel):
    session_id: EntityId
    messages: list[TableMessage] = Field(default_factory=list)


class OperatorCommandRequest(SchemaVersionedModel):
    command_type: OperatorCommandType
    requested_by: EntityId
    reason: str | None = None


class OperatorCommandResponse(SchemaVersionedModel):
    session_id: EntityId
    command_type: OperatorCommandType
    accepted: bool
    status: SessionStatus
    event: GameEvent | None = None


class ActionSubmissionRequest(SchemaVersionedModel):
    actor_id: EntityId
    source: ActionSubmissionSource
    turn: PlayerTurn


class ActionSubmissionResponse(SchemaVersionedModel):
    session_id: EntityId
    accepted: bool
    action_status: Literal["queued", "rejected", "validated"]
    normalized_action: ActionUnion | None = None


class TakeoverRequest(SchemaVersionedModel):
    actor_id: EntityId
    requested_by: EntityId | None = None


class TakeoverResponse(SchemaVersionedModel):
    session_id: EntityId
    actor_id: EntityId
    accepted: bool
    new_controller: ControllerType
    message: str | None = None


class StateEditRequest(SchemaVersionedModel):
    """Director state edits - limited to safe fields."""
    patches: list[dict] = Field(
        default_factory=list,
        description="List of {target_id, field, value} patches",
    )
    reason: NonEmptyString = "director_edit"


class StateEditResponse(SchemaVersionedModel):
    session_id: EntityId
    accepted: bool
    patches_applied: int = 0
    message: str | None = None


class RerunNarrationRequest(SchemaVersionedModel):
    reason: str | None = None


class RerunNarrationResponse(SchemaVersionedModel):
    session_id: EntityId
    accepted: bool
    narration_text: str | None = None
    message: str | None = None


class OverrideActionRequest(SchemaVersionedModel):
    turn: PlayerTurn
    reason: str | None = None


class OverrideActionResponse(SchemaVersionedModel):
    session_id: EntityId
    accepted: bool
    message: str | None = None


class WebSocketEventEnvelope(SchemaVersionedModel):
    session_id: EntityId
    sequence_number: int = Field(ge=0)
    event: GameEvent


class SessionStateResponse(SchemaVersionedModel):
    session: SessionSummary
    state: GameState
    recent_events: list[GameEvent] = Field(default_factory=list)


class HealthcheckResponse(SchemaVersionedModel):
    service: NonEmptyString
    status: Literal["ok"] = "ok"
