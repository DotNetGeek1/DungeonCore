from __future__ import annotations

from pydantic import Field

from .base import EntityId, NonEmptyString, SchemaVersionedModel
from .enums import ActionType, ActorRole
from .events import GameEvent
from .memory import MemoryEntry
from .messages import TableMessage
from .state import GameState


class CommunicationBudget(SchemaVersionedModel):
    max_messages: int = Field(ge=0)
    remaining_messages: int = Field(ge=0)
    max_message_length: int = Field(ge=1)


class AgentIdentity(SchemaVersionedModel):
    agent_id: EntityId
    actor_id: EntityId
    role: ActorRole
    name: NonEmptyString
    goals: list[NonEmptyString] = Field(default_factory=list)


class AgentContext(SchemaVersionedModel):
    session_id: EntityId
    identity: AgentIdentity
    scene_summary: str
    visible_state: GameState
    recent_events: list[GameEvent] = Field(default_factory=list)
    recent_messages: list[TableMessage] = Field(default_factory=list)
    memories: list[MemoryEntry] = Field(default_factory=list)
    allowed_actions: list[ActionType] = Field(default_factory=list)
    communication_budget: CommunicationBudget
