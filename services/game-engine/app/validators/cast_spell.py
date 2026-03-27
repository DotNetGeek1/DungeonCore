from __future__ import annotations

from typing import TYPE_CHECKING

from shared_schemas.actions import CastSpellBasicAction
from shared_schemas.state import GameState

from .base import ActionValidator, ValidationResult, MAX_MOVEMENT_SQUARES

if TYPE_CHECKING:
    from game_rules import RulesLoader


class CastSpellValidator(ActionValidator[CastSpellBasicAction]):
    def __init__(self, rules: RulesLoader | None = None) -> None:
        self.rules = rules

    def validate(self, action: CastSpellBasicAction, actor_id: str, state: GameState) -> ValidationResult:
        errors: list[str] = []

        if not self._actor_exists(actor_id, state):
            errors.append(f"Actor '{actor_id}' does not exist")
            return ValidationResult.failure(*errors)

        if not self._actor_can_act(actor_id, state):
            errors.append(f"Actor '{actor_id}' cannot act (dead or incapacitated)")
            return ValidationResult.failure(*errors)

        if not action.spell_id:
            errors.append("Spell ID is required")
            return ValidationResult.failure(*errors)

        if self.rules:
            spell = self.rules.get_spell(action.spell_id)
            if spell is None:
                errors.append(f"Unknown spell: '{action.spell_id}'")
                return ValidationResult.failure(*errors)

            if action.spell_slot_level is not None and spell.level > 0:
                if action.spell_slot_level < spell.level:
                    errors.append(
                        f"Spell '{spell.name}' requires at least a level {spell.level} slot "
                        f"(provided: {action.spell_slot_level})"
                    )
                    return ValidationResult.failure(*errors)

        if action.movement_path and len(action.movement_path) > MAX_MOVEMENT_SQUARES:
            errors.append(
                f"Movement path exceeds maximum of {MAX_MOVEMENT_SQUARES} squares "
                f"(requested: {len(action.movement_path)})"
            )
            return ValidationResult.failure(*errors)

        if action.target_id is not None:
            if not self._target_exists(action.target_id, state):
                errors.append(f"Target '{action.target_id}' does not exist")
                return ValidationResult.failure(*errors)

        if action.spell_slot_level is not None and action.spell_slot_level < 0:
            errors.append("Spell slot level cannot be negative")
            return ValidationResult.failure(*errors)

        if errors:
            return ValidationResult.failure(*errors)

        return ValidationResult.success(action)
