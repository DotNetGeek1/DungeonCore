from __future__ import annotations

from shared_schemas.actions import InspectAction
from shared_schemas.state import GameState

from .base import ActionValidator, ValidationResult


class InspectValidator(ActionValidator[InspectAction]):
    def validate(self, action: InspectAction, actor_id: str, state: GameState) -> ValidationResult:
        if not self._actor_exists(actor_id, state):
            return ValidationResult.failure(f"Actor '{actor_id}' does not exist")

        if not self._actor_can_act(actor_id, state):
            return ValidationResult.failure(f"Actor '{actor_id}' cannot act (dead or incapacitated)")

        if action.target_id is None and action.location_id is None:
            return ValidationResult.failure("Inspect action requires either target_id or location_id")

        return ValidationResult.success(action)
