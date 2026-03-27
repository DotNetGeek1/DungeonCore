from __future__ import annotations

import json
from typing import TYPE_CHECKING

from .registry import AgentTool, ToolParameter, ToolRegistry

if TYPE_CHECKING:
    from game_rules import RulesLoader


def register_rules_tools(registry: ToolRegistry, rules: RulesLoader | None) -> None:
    if rules is None:
        return

    def lookup_spell(spell_name: str) -> str:
        for spell in rules.spells().values():
            if spell.name.lower() == spell_name.lower() or spell.spell_id.lower() == spell_name.lower():
                return json.dumps({
                    "spell_id": spell.spell_id,
                    "name": spell.name,
                    "level": spell.level,
                    "school": spell.school.value,
                    "casting_time": f"{spell.casting_time.value} {spell.casting_time.unit}",
                    "range": f"{spell.range.value} {spell.range.unit}" if spell.range.value else spell.range.unit,
                    "components": {
                        "verbal": spell.components.verbal,
                        "somatic": spell.components.somatic,
                        "material": spell.components.material.description if spell.components.material else None,
                    },
                    "duration": f"{spell.duration.value} {spell.duration.unit}" if spell.duration.value else spell.duration.unit,
                    "concentration": spell.duration.concentration,
                    "effect": spell.effect.description[:300] if spell.effect.description else "",
                    "damage_dice": spell.effect.damage_dice,
                    "damage_type": spell.effect.damage_type,
                })
        return json.dumps({"error": f"Spell '{spell_name}' not found"})

    registry.register(AgentTool(
        name="lookup_spell",
        description="Look up a spell by name or ID to see its stats, range, damage, and effects.",
        parameters=[
            ToolParameter(name="spell_name", type="string", description="The name or ID of the spell to look up"),
        ],
        handler=lookup_spell,
    ))

    def lookup_weapon(weapon_id: str) -> str:
        weapon = rules.get_weapon(weapon_id)
        if weapon is None:
            for w in rules.weapons().values():
                if w.name.lower() == weapon_id.lower():
                    weapon = w
                    break
        if weapon is None:
            return json.dumps({"error": f"Weapon '{weapon_id}' not found"})
        result: dict = {
            "weapon_id": weapon.weapon_id,
            "name": weapon.name,
            "category": weapon.category.value,
            "damage_dice": weapon.damage_dice,
            "damage_type": weapon.damage_type,
            "properties": weapon.properties,
        }
        if weapon.range:
            result["range"] = {"normal": weapon.range.normal, "long": weapon.range.long}
        return json.dumps(result)

    registry.register(AgentTool(
        name="lookup_weapon",
        description="Look up a weapon by name or ID to see its damage, range, and properties.",
        parameters=[
            ToolParameter(name="weapon_id", type="string", description="The name or ID of the weapon"),
        ],
        handler=lookup_weapon,
    ))

    def check_condition(condition_name: str) -> str:
        condition = rules.get_condition(condition_name)
        if condition is None:
            for c in rules.conditions().values():
                if c.name.lower() == condition_name.lower():
                    condition = c
                    break
        if condition is None:
            return json.dumps({"error": f"Condition '{condition_name}' not found"})
        effects_desc = []
        for effect in condition.effects:
            desc = effect.type
            if effect.value is not None:
                desc += f": {effect.value}"
            effects_desc.append(desc)
        return json.dumps({
            "condition_id": condition.condition_id,
            "name": condition.name,
            "effects": effects_desc,
        })

    registry.register(AgentTool(
        name="check_condition",
        description="Look up a condition (e.g., prone, stunned, poisoned) to see its mechanical effects.",
        parameters=[
            ToolParameter(name="condition_name", type="string", description="The name or ID of the condition"),
        ],
        handler=check_condition,
    ))
