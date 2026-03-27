from __future__ import annotations

from shared_schemas.actions import MoveAction
from shared_schemas.state import GameState

from .base import ActionValidator, ValidationResult, MAX_MOVEMENT_SQUARES
from ..map_utils import validate_path_on_map


class MoveValidator(ActionValidator[MoveAction]):
    def validate(self, action: MoveAction, actor_id: str, state: GameState) -> ValidationResult:
        errors: list[str] = []

        if not self._actor_exists(actor_id, state):
            errors.append(f"Actor '{actor_id}' does not exist")
            return ValidationResult.failure(*errors)

        if not self._actor_can_act(actor_id, state):
            errors.append(f"Actor '{actor_id}' cannot act (dead or incapacitated)")
            return ValidationResult.failure(*errors)

        if not action.movement_path:
            errors.append("Movement path cannot be empty")
            return ValidationResult.failure(*errors)

        # Map-aware validation when dungeon_map is present
        if state.dungeon_map is not None:
            actor_pos = self._get_actor_position_xy(actor_id, state)
            if actor_pos is None:
                errors.append(f"Actor '{actor_id}' has no position on the map")
                return ValidationResult.failure(*errors)

            map_errors = validate_path_on_map(
                state.dungeon_map,
                actor_pos,
                list(action.movement_path),
                MAX_MOVEMENT_SQUARES,
            )
            if map_errors:
                return ValidationResult.failure(*map_errors)
        else:
            # Fallback: length-only validation
            if len(action.movement_path) > MAX_MOVEMENT_SQUARES:
                errors.append(
                    f"Movement path exceeds maximum of {MAX_MOVEMENT_SQUARES} squares "
                    f"(requested: {len(action.movement_path)})"
                )
                return ValidationResult.failure(*errors)

        if errors:
            return ValidationResult.failure(*errors)

        return ValidationResult.success(action)
