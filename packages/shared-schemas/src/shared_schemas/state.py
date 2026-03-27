from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from .base import EntityId, NonEmptyString, SchemaVersionedModel
from .enums import ActorRole, ControllerType, ScenePhase, Visibility

FlagValue = str | int | float | bool | None


class TerrainType(StrEnum):
    FLOOR = "floor"
    WALL = "wall"
    DOOR = "door"
    DOOR_LOCKED = "door_locked"
    STAIRS_UP = "stairs_up"
    STAIRS_DOWN = "stairs_down"
    DIFFICULT = "difficult"
    PIT = "pit"
    WATER_DEEP = "water_deep"


class TileContent(StrEnum):
    EMPTY = "empty"
    TREE = "tree"
    ALTAR = "altar"
    TREASURE_CHEST = "treasure_chest"
    CAMPFIRE = "campfire"
    PILLAR = "pillar"
    STATUE = "statue"
    BARREL = "barrel"
    TABLE = "table"
    TRAP = "trap"
    TRAP_HIDDEN = "trap_hidden"
    TORCH = "torch"
    RUBBLE = "rubble"
    BOOKSHELF = "bookshelf"
    FOUNTAIN = "fountain"
    LEVER = "lever"


class MapTile(SchemaVersionedModel):
    terrain: TerrainType = TerrainType.FLOOR
    content: TileContent = TileContent.EMPTY
    revealed: bool = False
    label: str | None = None
    elevation: int = 0
    door_open: bool = False  # Only relevant for DOOR/DOOR_LOCKED terrain types


class DungeonMap(SchemaVersionedModel):
    name: NonEmptyString
    width: int = Field(ge=1, le=100)
    height: int = Field(ge=1, le=100)
    tiles: list[list[MapTile]]
    default_terrain: TerrainType = TerrainType.FLOOR

    @model_validator(mode="after")
    def validate_tiles_dimensions(self) -> "DungeonMap":
        if len(self.tiles) != self.height:
            raise ValueError(
                f"tiles rows ({len(self.tiles)}) must equal height ({self.height})"
            )
        for row in self.tiles:
            if len(row) != self.width:
                raise ValueError(
                    f"tiles row length ({len(row)}) must equal width ({self.width})"
                )
        return self


class Position(SchemaVersionedModel):
    x: int
    y: int
    node_id: NonEmptyString | None = None
    zone_id: NonEmptyString | None = None


class ObjectiveState(SchemaVersionedModel):
    objective_id: EntityId
    label: NonEmptyString
    status: Literal["active", "completed", "failed"]
    summary: str | None = None


class VisibilityScope(SchemaVersionedModel):
    visibility: Visibility
    recipient_ids: list[EntityId] = Field(default_factory=list)


class ActorStateBase(SchemaVersionedModel):
    actor_id: EntityId
    name: NonEmptyString
    role: ActorRole
    hp: int = Field(ge=0)
    max_hp: int = Field(ge=1)
    ac: int = Field(ge=0)
    initiative: int = Field(default=0)
    position: Position | None = None
    status_effects: list[NonEmptyString] = Field(default_factory=list)
    inventory: list[NonEmptyString] = Field(default_factory=list)
    spell_slots: dict[NonEmptyString, int] = Field(default_factory=dict)
    alive: bool = True
    controller: ControllerType = ControllerType.AGENT
    visibility_scope: VisibilityScope = Field(
        default_factory=lambda: VisibilityScope(visibility=Visibility.PUBLIC)
    )


class CharacterState(ActorStateBase):
    role: Literal[ActorRole.PLAYER] = ActorRole.PLAYER
    character_class: NonEmptyString | None = None
    player_slot: NonEmptyString | None = None


class NpcState(ActorStateBase):
    role: Literal[ActorRole.NPC, ActorRole.ENEMY] = ActorRole.NPC
    disposition: Literal["ally", "neutral", "hostile"] = "neutral"
    behavior_tag: NonEmptyString | None = None


class SceneState(SchemaVersionedModel):
    scene_id: EntityId
    name: NonEmptyString
    summary: str
    phase: ScenePhase
    turn_number: int = Field(ge=0)
    active_actor_id: EntityId | None = None
    location_name: NonEmptyString | None = None


class TurnState(SchemaVersionedModel):
    turn_number: int = Field(ge=0)
    round_number: int = Field(ge=1)
    active_actor_id: EntityId | None = None
    phase: ScenePhase
    discussion_open: bool = False
    max_discussion_messages: int = Field(default=0, ge=0)
    remaining_discussion_messages: int = Field(default=0, ge=0)


class GameState(SchemaVersionedModel):
    campaign_id: EntityId
    session_id: EntityId
    scene: SceneState
    turn: TurnState
    characters: dict[EntityId, CharacterState] = Field(default_factory=dict)
    npcs: dict[EntityId, NpcState] = Field(default_factory=dict)
    objectives: list[ObjectiveState] = Field(default_factory=list)
    flags: dict[NonEmptyString, FlagValue] = Field(default_factory=dict)
    dungeon_map: DungeonMap | None = None
