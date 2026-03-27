from __future__ import annotations

from shared_schemas.actions import MoveAndAttackAction
from shared_schemas.state import GameState

from .base import ActionValidator, ValidationResult, MAX_MOVEMENT_SQUARES
from ..map_utils import validate_path_on_map, chebyshev_distance, parse_coord

MELEE_REACH_SQUARES = 1


class MoveAndAttackValidator(ActionValidator[MoveAndAttackAction]):
    def validate(self, action: MoveAndAttackAction, actor_id: str, state: GameState) -> ValidationResult:
        errors: list[str] = []

        if not self._actor_exists(actor_id, state):
            errors.append(f"Actor '{actor_id}' does not exist")
            return ValidationResult.failure(*errors)

        if not self._actor_can_act(actor_id, state):
            errors.append(f"Actor '{actor_id}' cannot act (dead or incapacitated)")
            return ValidationResult.failure(*errors)

        if not action.movement_path:
            errors.append("Movement path cannot be empty for move_and_attack")
            return ValidationResult.failure(*errors)

        if not self._target_exists(action.target_id, state):
            errors.append(f"Target '{action.target_id}' does not exist")
            return ValidationResult.failure(*errors)

        if not self._target_is_alive(action.target_id, state):
            errors.append(f"Target '{action.target_id}' is not alive")
            return ValidationResult.failure(*errors)

        if action.target_id == actor_id:
            errors.append("Cannot attack yourself")
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

            # Verify the final position is adjacent to the target
            last_coord_str = action.movement_path[-1]
            last_coords = parse_coord(last_coord_str)
            target_pos = self._get_actor_position_xy(action.target_id, state)
            if last_coords is not None and target_pos is not None:
                dist = chebyshev_distance(last_coords[0], last_coords[1], target_pos.x, target_pos.y)
                if dist > MELEE_REACH_SQUARES:
                    errors.append(
                        f"Final position ({last_coords[0]},{last_coords[1]}) is not adjacent "
                        f"to target '{action.target_id}' at ({target_pos.x},{target_pos.y})"
                    )
                    return ValidationResult.failure(*errors)
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
