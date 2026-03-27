from __future__ import annotations

from shared_schemas.actions import DefendAction
from shared_schemas.state import GameState

from .base import ActionValidator, ValidationResult


class DefendValidator(ActionValidator[DefendAction]):
    def validate(self, action: DefendAction, actor_id: str, state: GameState) -> ValidationResult:
        errors: list[str] = []

        if not self._actor_exists(actor_id, state):
            errors.append(f"Actor '{actor_id}' does not exist")
            return ValidationResult.failure(*errors)

        if not self._actor_can_act(actor_id, state):
            errors.append(f"Actor '{actor_id}' cannot act (dead or incapacitated)")
            return ValidationResult.failure(*errors)

        valid_stances = ["guard", "dodge", "brace"]
        if action.stance not in valid_stances:
            errors.append(f"Invalid stance '{action.stance}'. Must be one of: {valid_stances}")
            return ValidationResult.failure(*errors)

        if errors:
            return ValidationResult.failure(*errors)

        return ValidationResult.success(action)
