from __future__ import annotations

from shared_schemas.actions import AttackAction
from shared_schemas.state import GameState

from .base import ActionValidator, ValidationResult
from ..map_utils import chebyshev_distance

MELEE_REACH_SQUARES = 1


class AttackValidator(ActionValidator[AttackAction]):
    def validate(self, action: AttackAction, actor_id: str, state: GameState) -> ValidationResult:
        errors: list[str] = []

        if not self._actor_exists(actor_id, state):
            errors.append(f"Actor '{actor_id}' does not exist")
            return ValidationResult.failure(*errors)

        if not self._actor_can_act(actor_id, state):
            errors.append(f"Actor '{actor_id}' cannot act (dead or incapacitated)")
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

        # Range check when map is present
        if state.dungeon_map is not None:
            actor_pos = self._get_actor_position_xy(actor_id, state)
            target_pos = self._get_actor_position_xy(action.target_id, state)
            if actor_pos is not None and target_pos is not None:
                dist = chebyshev_distance(actor_pos.x, actor_pos.y, target_pos.x, target_pos.y)
                if dist > MELEE_REACH_SQUARES:
                    errors.append(
                        f"Target '{action.target_id}' is out of melee reach "
                        f"(distance {dist}, max {MELEE_REACH_SQUARES} square(s))"
                    )
                    return ValidationResult.failure(*errors)

        if errors:
            return ValidationResult.failure(*errors)

        return ValidationResult.success(action)
