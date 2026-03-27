from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AliasChoices, Field, model_validator

from .base import EntityId, NonEmptyString, SchemaVersionedModel
from .enums import ActionType


class AttackAction(SchemaVersionedModel):
    type: Literal[ActionType.ATTACK] = ActionType.ATTACK
    target_id: EntityId
    movement_path: list[NonEmptyString] = Field(default_factory=list)
    weapon_id: EntityId | None = None


class MoveAction(SchemaVersionedModel):
    type: Literal[ActionType.MOVE] = ActionType.MOVE
    movement_path: list[NonEmptyString] = Field(min_length=1)


class MoveAndAttackAction(SchemaVersionedModel):
    type: Literal[ActionType.MOVE_AND_ATTACK] = ActionType.MOVE_AND_ATTACK
    movement_path: list[NonEmptyString] = Field(min_length=1)
    target_id: EntityId
    weapon_id: EntityId | None = None


class DefendAction(SchemaVersionedModel):
    type: Literal[ActionType.DEFEND] = ActionType.DEFEND
    stance: Literal["guard", "dodge", "brace"] = "guard"


class InspectAction(SchemaVersionedModel):
    type: Literal[ActionType.INSPECT] = ActionType.INSPECT
    target_id: EntityId | None = None
    location_id: EntityId | None = None
    detail: str | None = None

    @model_validator(mode="after")
    def validate_target(self) -> "InspectAction":
        if self.target_id is None and self.location_id is None:
            raise ValueError("inspect actions require either target_id or location_id")
        return self


class InteractAction(SchemaVersionedModel):
    """Interact with an object in the environment (pickup, use, open, pull, etc.)."""
    type: Literal[ActionType.INTERACT] = ActionType.INTERACT
    target_id: EntityId
    interaction_type: Literal["pickup", "use", "open", "close", "pull", "push"] = "pickup"
    detail: str | None = None


class CastSpellBasicAction(SchemaVersionedModel):
    type: Literal[ActionType.CAST_SPELL_BASIC] = ActionType.CAST_SPELL_BASIC
    spell_id: EntityId
    target_id: EntityId | None = None
    movement_path: list[NonEmptyString] = Field(default_factory=list)
    spell_slot_level: int | None = Field(default=None, ge=0)


class TileChange(SchemaVersionedModel):
    """A single tile mutation in an UpdateMapAction."""
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    terrain: str | None = None
    content: str | None = None
    revealed: bool | None = None
    label: str | None = None
    elevation: int | None = None


class UpdateMapAction(SchemaVersionedModel):
    type: Literal[ActionType.UPDATE_MAP] = ActionType.UPDATE_MAP
    changes: list[TileChange] = Field(min_length=1)
    map_name: str | None = None


ActionUnion = Annotated[
    AttackAction
    | MoveAction
    | MoveAndAttackAction
    | DefendAction
    | InspectAction
    | InteractAction
    | CastSpellBasicAction
    | UpdateMapAction,
    Field(discriminator="type"),
]


class PlayerTurn(SchemaVersionedModel):
    thought: str | None = Field(
        default=None,
        validation_alias=AliasChoices("thought", "private_thought"),
    )
    speech: str | None = Field(
        default=None,
        validation_alias=AliasChoices("speech", "in_character_speech"),
    )
    table_talk: str | None = None
    action: ActionUnion | None = None

    @model_validator(mode="after")
    def validate_turn_payload(self) -> "PlayerTurn":
        if self.speech is None and self.table_talk is None and self.action is None:
            raise ValueError("player turns require speech, table_talk, or action")
        return self
