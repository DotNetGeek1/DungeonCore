from __future__ import annotations

import json
from typing import TYPE_CHECKING

from .registry import AgentTool, ToolParameter, ToolRegistry

if TYPE_CHECKING:
    from shared_schemas.state import GameState


def register_validation_tools(registry: ToolRegistry, state: GameState | None) -> None:
    if state is None:
        return

    def check_action_validity(action_type: str, target_id: str = "", **kwargs: str) -> str:
        """Pre-validate an action before committing. Lightweight check only."""
        issues = []

        valid_actions = {"attack", "move", "move_and_attack", "defend", "inspect", "interact", "cast_spell_basic"}
        if action_type not in valid_actions:
            issues.append(f"Unknown action type: {action_type}")
            return json.dumps({"valid": False, "issues": issues})

        if action_type in ("attack", "move_and_attack") and not target_id:
            issues.append("Attack actions require a target_id")

        if action_type == "interact" and not target_id:
            issues.append("Interact actions require a target_id")

        if target_id:
            all_ids = set(state.characters.keys()) | set(state.npcs.keys())
            if target_id not in all_ids:
                issues.append(f"Target '{target_id}' not found among visible entities")
            else:
                target_char = state.characters.get(target_id)
                target_npc = state.npcs.get(target_id)
                target_entity = target_char or target_npc
                if target_entity and not target_entity.alive:
                    issues.append(f"Target '{target_id}' is not alive")

        if action_type == "cast_spell_basic":
            spell_id = kwargs.get("spell_id", "")
            if not spell_id:
                issues.append("cast_spell_basic requires a spell_id")

        return json.dumps({
            "valid": len(issues) == 0,
            "action_type": action_type,
            "target_id": target_id,
            "issues": issues,
        })

    registry.register(AgentTool(
        name="check_action_validity",
        description="Pre-check whether an action is likely valid before committing. Checks target exists and is alive, action type is known, and required fields are present.",
        parameters=[
            ToolParameter(name="action_type", type="string", description="The action type to check", enum=["attack", "move", "move_and_attack", "defend", "inspect", "interact", "cast_spell_basic"]),
            ToolParameter(name="target_id", type="string", description="The target entity ID (if applicable)", required=False),
        ],
        handler=check_action_validity,
    ))
