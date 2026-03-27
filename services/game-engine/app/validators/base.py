from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Generic, TypeVar

from shared_schemas.actions import ActionUnion
from shared_schemas.state import GameState, Position

MAX_MOVEMENT_SQUARES = 8


@dataclass
class ValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    normalized_action: ActionUnion | None = None

    @classmethod
    def success(cls, action: ActionUnion | None = None) -> "ValidationResult":
        return cls(valid=True, normalized_action=action)

    @classmethod
    def failure(cls, *errors: str) -> "ValidationResult":
        return cls(valid=False, errors=list(errors))


T = TypeVar("T", bound=ActionUnion)


class ActionValidator(ABC, Generic[T]):
    @abstractmethod
    def validate(self, action: T, actor_id: str, state: GameState) -> ValidationResult:
        pass

    def _actor_exists(self, actor_id: str, state: GameState) -> bool:
        return actor_id in state.characters or actor_id in state.npcs

    def _actor_can_act(self, actor_id: str, state: GameState) -> bool:
        if actor_id in state.characters:
            actor = state.characters[actor_id]
        elif actor_id in state.npcs:
            actor = state.npcs[actor_id]
        else:
            return False
        return actor.alive and actor.hp > 0

    def _target_exists(self, target_id: str, state: GameState) -> bool:
        return target_id in state.characters or target_id in state.npcs

    def _target_is_alive(self, target_id: str, state: GameState) -> bool:
        if target_id in state.characters:
            char = state.characters[target_id]
            return char.alive and char.hp > 0
        if target_id in state.npcs:
            npc = state.npcs[target_id]
            return npc.alive and npc.hp > 0
        return False

    def _get_actor_position(self, actor_id: str, state: GameState) -> str | None:
        """Returns the node_id string of the actor's position (legacy)."""
        if actor_id in state.characters:
            pos = state.characters[actor_id].position
            return pos.node_id if pos else None
        if actor_id in state.npcs:
            pos = state.npcs[actor_id].position
            return pos.node_id if pos else None
        return None

    def _get_actor_position_xy(self, actor_id: str, state: GameState) -> Position | None:
        """Returns the full Position object for the actor (with x, y coords)."""
        if actor_id in state.characters:
            return state.characters[actor_id].position
        if actor_id in state.npcs:
            return state.npcs[actor_id].position
        return None
