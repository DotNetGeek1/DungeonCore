from __future__ import annotations

from shared_schemas.actions import InteractAction
from shared_schemas.state import GameState, TerrainType

from .base import ActionValidator, ValidationResult


class InteractValidator(ActionValidator[InteractAction]):
    """Validates interact actions (pickup, use, open, etc.)."""

    def validate(self, action: InteractAction, actor_id: str, state: GameState) -> ValidationResult:
        if not self._actor_exists(actor_id, state):
            return ValidationResult.failure(f"Actor '{actor_id}' does not exist")

        if not self._actor_can_act(actor_id, state):
            return ValidationResult.failure(f"Actor '{actor_id}' cannot act (dead or incapacitated)")

        if not action.target_id:
            return ValidationResult.failure("Interact action requires a target_id")

        valid_types = {"pickup", "use", "open", "close", "pull", "push"}
        if action.interaction_type not in valid_types:
            return ValidationResult.failure(
                f"Invalid interaction_type '{action.interaction_type}'. "
                f"Must be one of: {', '.join(valid_types)}"
            )

        # Check adjacency for door interactions
        if action.target_id.startswith("door:") and action.interaction_type in ("open", "close"):
            coords = self._parse_door_target(action.target_id)
            if coords:
                x, y = coords
                actor = state.characters.get(actor_id) or state.npcs.get(actor_id)
                if actor and actor.position:
                    dx = abs(actor.position.x - x)
                    dy = abs(actor.position.y - y)
                    if dx > 1 or dy > 1:
                        return ValidationResult.failure(
                            f"Must be adjacent to the door at ({x},{y}) to {action.interaction_type} it. "
                            f"You are at ({actor.position.x},{actor.position.y}), which is {max(dx, dy)} tiles away. "
                            f"Move closer first using a 'move' action."
                        )

        return ValidationResult.success(action)

    def _parse_door_target(self, target_id: str) -> tuple[int, int] | None:
        """Parse door:x,y format to coordinates."""
        if not target_id.startswith("door:"):
            return None
        try:
            coords = target_id[5:]
            parts = coords.split(",")
            if len(parts) == 2:
                return int(parts[0].strip()), int(parts[1].strip())
        except (ValueError, AttributeError):
            pass
        return None
