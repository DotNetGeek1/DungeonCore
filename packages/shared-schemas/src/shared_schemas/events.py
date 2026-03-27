from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field

from .actions import ActionUnion, PlayerTurn
from .base import CorrelationId, EntityId, NonEmptyString, TraceId, TimestampedModel
from .enums import ActionType, ControllerType, ScenePhase
from .messages import TableMessage
from .state import GameState


class EventEnvelopeBase(TimestampedModel):
    id: EntityId
    session_id: EntityId
    turn_number: int = Field(ge=0)
    trace_id: TraceId
    correlation_id: CorrelationId


class SessionStartedPayload(TimestampedModel):
    session_id: EntityId
    campaign_id: EntityId
    started_by: EntityId | None = None
    initial_state: GameState


class SceneStartedPayload(TimestampedModel):
    scene_id: EntityId
    scene_name: NonEmptyString
    phase: ScenePhase
    active_actor_id: EntityId | None = None


class DiscussionWindowPayload(TimestampedModel):
    scene_id: EntityId
    active_actor_id: EntityId | None = None
    max_messages: int = Field(ge=0)


class MessageCreatedPayload(TimestampedModel):
    message: TableMessage


class ActionProposedPayload(TimestampedModel):
    actor_id: EntityId
    turn: PlayerTurn


class ActionValidatedPayload(TimestampedModel):
    actor_id: EntityId
    valid: bool
    normalized_action: ActionUnion | None = None
    errors: list[NonEmptyString] = Field(default_factory=list)


class DiceRollRecord(TimestampedModel):
    die: NonEmptyString
    value: int = Field(ge=1)
    modifier: int = 0
    total: int


class DiceRolledPayload(TimestampedModel):
    actor_id: EntityId
    action_type: NonEmptyString
    rolls: list[DiceRollRecord] = Field(min_length=1)


class StateUpdatedPayload(TimestampedModel):
    state: GameState
    reason: NonEmptyString


class NarrationEmittedPayload(TimestampedModel):
    narrator_id: EntityId
    text: NonEmptyString


class StatePatchRecord(TimestampedModel):
    patch_type: NonEmptyString
    target_id: EntityId
    field: NonEmptyString
    old_value: object
    new_value: object


class ActionResolvedPayload(TimestampedModel):
    actor_id: EntityId
    action_type: NonEmptyString
    success: bool
    description: NonEmptyString
    dice_rolls: list[DiceRollRecord] = Field(default_factory=list)
    state_patches: list[StatePatchRecord] = Field(default_factory=list)
    hit: bool | None = None
    damage: int | None = None


class ActionAwaitingHumanPayload(TimestampedModel):
    actor_id: EntityId
    allowed_actions: list[ActionType] = Field(default_factory=list)
    timeout_seconds: int = Field(ge=0, default=120)


class TakeoverChangedPayload(TimestampedModel):
    actor_id: EntityId
    new_controller: ControllerType
    previous_controller: ControllerType


class TurnEndedPayload(TimestampedModel):
    actor_id: EntityId
    next_actor_id: EntityId | None = None
    phase: ScenePhase


class MapUpdatedPayload(TimestampedModel):
    map_name: NonEmptyString
    changes_count: int = Field(ge=0)
    full_map_included: bool = False


class SessionStartedEvent(EventEnvelopeBase):
    event_type: Literal["session.started"] = "session.started"
    payload: SessionStartedPayload


class SceneStartedEvent(EventEnvelopeBase):
    event_type: Literal["scene.started"] = "scene.started"
    payload: SceneStartedPayload


class DiscussionOpenedEvent(EventEnvelopeBase):
    event_type: Literal["discussion.opened"] = "discussion.opened"
    payload: DiscussionWindowPayload


class DiscussionClosedEvent(EventEnvelopeBase):
    event_type: Literal["discussion.closed"] = "discussion.closed"
    payload: DiscussionWindowPayload


class MessageCreatedEvent(EventEnvelopeBase):
    event_type: Literal["message.created"] = "message.created"
    payload: MessageCreatedPayload


class ActionProposedEvent(EventEnvelopeBase):
    event_type: Literal["action.proposed"] = "action.proposed"
    payload: ActionProposedPayload


class ActionValidatedEvent(EventEnvelopeBase):
    event_type: Literal["action.validated"] = "action.validated"
    payload: ActionValidatedPayload


class DiceRolledEvent(EventEnvelopeBase):
    event_type: Literal["dice.rolled"] = "dice.rolled"
    payload: DiceRolledPayload


class StateUpdatedEvent(EventEnvelopeBase):
    event_type: Literal["state.updated"] = "state.updated"
    payload: StateUpdatedPayload


class NarrationEmittedEvent(EventEnvelopeBase):
    event_type: Literal["narration.emitted"] = "narration.emitted"
    payload: NarrationEmittedPayload


class ActionResolvedEvent(EventEnvelopeBase):
    event_type: Literal["action.resolved"] = "action.resolved"
    payload: ActionResolvedPayload


class ActionAwaitingHumanEvent(EventEnvelopeBase):
    event_type: Literal["action.awaiting_human"] = "action.awaiting_human"
    payload: ActionAwaitingHumanPayload


class TakeoverChangedEvent(EventEnvelopeBase):
    event_type: Literal["takeover.changed"] = "takeover.changed"
    payload: TakeoverChangedPayload


class TurnEndedEvent(EventEnvelopeBase):
    event_type: Literal["turn.ended"] = "turn.ended"
    payload: TurnEndedPayload


class MapUpdatedEvent(EventEnvelopeBase):
    event_type: Literal["map.updated"] = "map.updated"
    payload: MapUpdatedPayload


GameEvent = Annotated[
    SessionStartedEvent
    | SceneStartedEvent
    | DiscussionOpenedEvent
    | DiscussionClosedEvent
    | MessageCreatedEvent
    | ActionProposedEvent
    | ActionValidatedEvent
    | DiceRolledEvent
    | StateUpdatedEvent
    | ActionResolvedEvent
    | ActionAwaitingHumanEvent
    | TakeoverChangedEvent
    | NarrationEmittedEvent
    | TurnEndedEvent
    | MapUpdatedEvent,
    Field(discriminator="event_type"),
]
