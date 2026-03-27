from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Literal
import uuid

from shared_schemas.actions import ActionUnion, AttackAction, CastSpellBasicAction, DefendAction, InteractAction, MoveAction, MoveAndAttackAction
from shared_schemas.enums import ActionType
from shared_schemas.state import GameState, Position, TerrainType

from ..dice import DiceRoll, DiceRoller

if TYPE_CHECKING:
    from game_rules import RulesLoader


DEFAULT_ATTACK_MODIFIER = 5
DEFAULT_DAMAGE_DIE = "d8"
DEFAULT_DAMAGE_MODIFIER = 3
DEFAULT_SPELL_ATTACK_MODIFIER = 4
DEFAULT_SPELL_DAMAGE_DIE = "d10"
DEFAULT_SPELL_DAMAGE_COUNT = 1
DEFAULT_SPELL_DAMAGE_MODIFIER = 0


@dataclass
class StatePatch:
    patch_type: str
    target_id: str
    field: str
    old_value: object
    new_value: object


@dataclass
class ResolutionResult:
    success: bool
    action_type: ActionType
    dice_rolls: list[DiceRoll] = field(default_factory=list)
    state_patches: list[StatePatch] = field(default_factory=list)
    description: str = ""
    hit: bool | None = None
    damage: int | None = None


class CombatResolver:
    def __init__(
        self,
        dice_roller: DiceRoller | None = None,
        rules: RulesLoader | None = None,
        inspectable_objects: dict[str, dict] | None = None,
    ) -> None:
        self.dice = dice_roller or DiceRoller()
        self.rules = rules
        self.inspectable_objects = inspectable_objects or {}

    def _clear_defending_status(self, actor_id: str, state: GameState) -> list[StatePatch]:
        """Remove any defending:* status effects from the actor taking their turn."""
        patches: list[StatePatch] = []
        effects: list[str] = []
        if actor_id in state.characters:
            effects = list(state.characters[actor_id].status_effects)
        elif actor_id in state.npcs:
            effects = list(state.npcs[actor_id].status_effects)

        defending = [e for e in effects if e.startswith("defending:")]
        if defending:
            new_effects = [e for e in effects if not e.startswith("defending:")]
            patches.append(StatePatch(
                patch_type="clear_defend",
                target_id=actor_id,
                field="status_effects",
                old_value=effects,
                new_value=new_effects,
            ))
        return patches

    def resolve(self, action: ActionUnion, actor_id: str, state: GameState) -> ResolutionResult:
        clear_patches = self._clear_defending_status(actor_id, state)

        result = self._resolve_action(action, actor_id, state)

        if clear_patches and result.success:
            result.state_patches = clear_patches + result.state_patches

        return result

    def _resolve_action(self, action: ActionUnion, actor_id: str, state: GameState) -> ResolutionResult:
        match action.type:
            case ActionType.ATTACK:
                return self._resolve_attack(action, actor_id, state)
            case ActionType.MOVE:
                return self._resolve_move(action, actor_id, state)
            case ActionType.MOVE_AND_ATTACK:
                return self._resolve_move_and_attack(action, actor_id, state)
            case ActionType.DEFEND:
                return self._resolve_defend(action, actor_id, state)
            case ActionType.INSPECT:
                return self._resolve_inspect(action, actor_id, state)
            case ActionType.INTERACT:
                return self._resolve_interact(action, actor_id, state)
            case ActionType.CAST_SPELL_BASIC:
                return self._resolve_cast_spell(action, actor_id, state)
            case _:
                return ResolutionResult(
                    success=False,
                    action_type=action.type,
                    description=f"Unknown action type: {action.type}",
                )

    def _get_actor_attack_modifier(self, actor_id: str, state: GameState) -> int:
        CLASS_ATTACK_MODIFIERS = {
            "fighter": 6,   # STR 16 (+3) + proficiency (+3)
            "rogue": 6,     # DEX 16 (+3) + proficiency (+3)
            "wizard": 3,    # STR 8 (-1) + proficiency (+2) + 2 (arcane)
            "cleric": 5,    # STR 14 (+2) + proficiency (+3)
            "ranger": 5,    # DEX 14 (+2) + proficiency (+3)
            "paladin": 6,   # STR 16 (+3) + proficiency (+3)
            "barbarian": 6, # STR 16 (+3) + proficiency (+3)
            "bard": 4,      # DEX 12 (+1) + proficiency (+3)
            "warlock": 4,   # CHA-based but melee = DEX 12 (+1) + proficiency (+3)
        }
        NPC_ATTACK_MODIFIER = 4  # generic NPC: +2 ability + 2 proficiency

        if actor_id in state.characters:
            char_class = state.characters[actor_id].character_class
            if char_class:
                return CLASS_ATTACK_MODIFIERS.get(char_class.lower(), DEFAULT_ATTACK_MODIFIER)
            return DEFAULT_ATTACK_MODIFIER
        if actor_id in state.npcs:
            return NPC_ATTACK_MODIFIER
        return DEFAULT_ATTACK_MODIFIER

    def _get_target_ac(self, target_id: str, state: GameState) -> int:
        ac = 10
        effects: list[str] = []
        if target_id in state.characters:
            ac = state.characters[target_id].ac
            effects = state.characters[target_id].status_effects
        elif target_id in state.npcs:
            ac = state.npcs[target_id].ac
            effects = state.npcs[target_id].status_effects

        if "defending:guard" in effects:
            ac += 2

        return ac

    def _get_damage_info(self, actor_id: str, state: GameState, weapon_id: str | None = None) -> tuple[str, int, int]:
        """Returns (die, count, modifier) for the actor's damage roll."""
        CLASS_DAMAGE_MODIFIERS = {
            "fighter": 3,    # STR 16 (+3)
            "rogue": 3,      # DEX 16 (+3)
            "barbarian": 4,  # STR 18 (+4) with rage
            "paladin": 3,    # STR 16 (+3)
        }

        def _class_mod(aid: str) -> int:
            if aid in state.characters:
                cc = state.characters[aid].character_class
                if cc:
                    return CLASS_DAMAGE_MODIFIERS.get(cc.lower(), DEFAULT_DAMAGE_MODIFIER)
            return DEFAULT_DAMAGE_MODIFIER

        def _from_notation(notation: str, aid: str) -> tuple[str, int, int]:
            count, die = self._parse_dice_notation(notation)
            return die, count, _class_mod(aid)

        if weapon_id and self.rules:
            weapon = self.rules.get_weapon(weapon_id)
            if weapon and weapon.damage_dice:
                return _from_notation(weapon.damage_dice, actor_id)

        if self.rules and actor_id in state.characters:
            inventory = state.characters[actor_id].inventory
            for item_id in inventory:
                weapon = self.rules.get_weapon(item_id)
                if weapon and weapon.damage_dice:
                    return _from_notation(weapon.damage_dice, actor_id)

        return DEFAULT_DAMAGE_DIE, 1, _class_mod(actor_id)

    def _apply_damage(
        self, target_id: str, damage: int, state: GameState, patches: list[StatePatch],
    ) -> tuple[int, int]:
        """Apply damage and append HP patch (+ alive=False if reduced to 0)."""
        old_hp = 0
        if target_id in state.characters:
            old_hp = state.characters[target_id].hp
        elif target_id in state.npcs:
            old_hp = state.npcs[target_id].hp
        else:
            return 0, 0

        new_hp = max(0, old_hp - damage)

        patches.append(
            StatePatch(
                patch_type="damage",
                target_id=target_id,
                field="hp",
                old_value=old_hp,
                new_value=new_hp,
            )
        )

        if new_hp <= 0 and old_hp > 0:
            patches.append(
                StatePatch(
                    patch_type="death",
                    target_id=target_id,
                    field="alive",
                    old_value=True,
                    new_value=False,
                )
            )

        return old_hp, new_hp

    def _resolve_attack(self, action: AttackAction, actor_id: str, state: GameState) -> ResolutionResult:
        dice_rolls: list[DiceRoll] = []
        patches: list[StatePatch] = []

        attack_mod = self._get_actor_attack_modifier(actor_id, state)
        attack_roll = self.dice.roll_d20(attack_mod)
        dice_rolls.append(attack_roll)

        target_ac = self._get_target_ac(action.target_id, state)
        hit = attack_roll.total >= target_ac

        damage = 0
        if hit:
            weapon_id = getattr(action, "weapon_id", None)
            die, count, modifier = self._get_damage_info(actor_id, state, weapon_id=weapon_id)
            damage_rolls = self.dice.roll_damage(die, count, modifier)
            dice_rolls.extend(damage_rolls)
            damage = sum(r.total for r in damage_rolls)

            self._apply_damage(action.target_id, damage, state, patches)

        return ResolutionResult(
            success=True,
            action_type=ActionType.ATTACK,
            dice_rolls=dice_rolls,
            state_patches=patches,
            hit=hit,
            damage=damage if hit else None,
            description=f"Attack {'hits' if hit else 'misses'} (rolled {attack_roll.total} vs AC {target_ac})"
            + (f", dealing {damage} damage" if hit else ""),
        )

    def _resolve_move(self, action: MoveAction, actor_id: str, state: GameState) -> ResolutionResult:
        patches: list[StatePatch] = []

        old_position_str = None
        old_value = None
        pos = None
        if actor_id in state.characters:
            pos = state.characters[actor_id].position
        elif actor_id in state.npcs:
            pos = state.npcs[actor_id].position

        if pos:
            old_position_str = pos.node_id or f"{pos.x},{pos.y}"
            old_value = {"x": pos.x, "y": pos.y, "node_id": old_position_str}

        new_position_coord = action.movement_path[-1] if action.movement_path else None
        new_value = None
        if new_position_coord:
            parts = new_position_coord.split(",")
            if len(parts) == 2:
                try:
                    new_x = int(parts[0].strip())
                    new_y = int(parts[1].strip())
                    new_value = {"x": new_x, "y": new_y, "node_id": new_position_coord}
                except ValueError:
                    new_value = {"x": 0, "y": 0, "node_id": new_position_coord}
            else:
                new_value = {"x": 0, "y": 0, "node_id": new_position_coord}

        patches.append(
            StatePatch(
                patch_type="move",
                target_id=actor_id,
                field="position",
                old_value=old_value,
                new_value=new_value,
            )
        )

        return ResolutionResult(
            success=True,
            action_type=ActionType.MOVE,
            dice_rolls=[],
            state_patches=patches,
            description=f"Moved from {old_position_str or 'unknown'} to {new_position_coord or 'unknown'}",
        )

    def _resolve_move_and_attack(
        self, action: MoveAndAttackAction, actor_id: str, state: GameState
    ) -> ResolutionResult:
        move_result = self._resolve_move(
            MoveAction(type=ActionType.MOVE, movement_path=action.movement_path),
            actor_id,
            state,
        )

        attack_result = self._resolve_attack(
            AttackAction(
                type=ActionType.ATTACK,
                target_id=action.target_id,
                weapon_id=action.weapon_id,
            ),
            actor_id,
            state,
        )

        return ResolutionResult(
            success=True,
            action_type=ActionType.MOVE_AND_ATTACK,
            dice_rolls=attack_result.dice_rolls,
            state_patches=move_result.state_patches + attack_result.state_patches,
            hit=attack_result.hit,
            damage=attack_result.damage,
            description=f"{move_result.description}; {attack_result.description}",
        )

    def _resolve_defend(self, action: DefendAction, actor_id: str, state: GameState) -> ResolutionResult:
        patches: list[StatePatch] = []

        stance_effects = {
            "guard": "defending:guard",
            "dodge": "defending:dodge",
            "brace": "defending:brace",
        }
        stance_descriptions = {
            "guard": "raises their guard (+2 AC until next turn)",
            "dodge": "focuses on evasion (advantage on Dex saves until next turn)",
            "brace": "braces for impact (halve next incoming damage)",
        }

        effect = stance_effects.get(action.stance, "defending:guard")

        current_effects = []
        if actor_id in state.characters:
            current_effects = list(state.characters[actor_id].status_effects)
        elif actor_id in state.npcs:
            current_effects = list(state.npcs[actor_id].status_effects)

        old_effects = list(current_effects)
        current_effects = [e for e in current_effects if not e.startswith("defending:")]
        current_effects.append(effect)

        patches.append(StatePatch(
            patch_type="defend",
            target_id=actor_id,
            field="status_effects",
            old_value=old_effects,
            new_value=current_effects,
        ))

        desc = stance_descriptions.get(action.stance, "takes a defensive posture")

        return ResolutionResult(
            success=True,
            action_type=ActionType.DEFEND,
            dice_rolls=[],
            state_patches=patches,
            description=f"{desc}",
        )

    def _resolve_inspect(self, action, actor_id: str, state: GameState) -> ResolutionResult:
        target_key = action.target_id or action.location_id or "unknown"
        dice_rolls: list[DiceRoll] = []
        patches: list[StatePatch] = []
        description_parts: list[str] = []

        obj = self.inspectable_objects.get(target_key)
        if obj is None:
            for key, val in self.inspectable_objects.items():
                if val.get("object_id") == target_key or val.get("location") == target_key:
                    obj = val
                    target_key = key
                    break

        if obj is None:
            return ResolutionResult(
                success=True,
                action_type=ActionType.INSPECT,
                dice_rolls=[],
                state_patches=[],
                description=f"Examines {target_key} but finds nothing of note.",
            )

        investigation_roll = self.dice.roll_d20(2)
        dice_rolls.append(investigation_roll)

        base_dc = obj.get("inspect_dc", 10)
        if investigation_roll.total >= base_dc:
            description_parts.append(obj.get("description", f"Examines {obj.get('name', target_key)}."))
            flag_key = f"{target_key}_examined"
            if flag_key in state.flags and not state.flags[flag_key]:
                patches.append(StatePatch(
                    patch_type="flag",
                    target_id="flags",
                    field=flag_key,
                    old_value=False,
                    new_value=True,
                ))
        else:
            description_parts.append(
                f"Examines {obj.get('name', target_key)} but doesn't notice anything unusual "
                f"(rolled {investigation_roll.total} vs DC {base_dc})."
            )

        for secret_name, secret in obj.get("secrets", {}).items():
            secret_dc = secret.get("dc", 15)
            if investigation_roll.total >= secret_dc:
                description_parts.append(secret.get("description", f"Discovers {secret_name}."))

                flag_key = secret_name
                if flag_key in state.flags and not state.flags[flag_key]:
                    patches.append(StatePatch(
                        patch_type="flag",
                        target_id="flags",
                        field=flag_key,
                        old_value=False,
                        new_value=True,
                    ))

        return ResolutionResult(
            success=True,
            action_type=ActionType.INSPECT,
            dice_rolls=dice_rolls,
            state_patches=patches,
            description=" ".join(description_parts),
        )

    def _resolve_interact(self, action: InteractAction, actor_id: str, state: GameState) -> ResolutionResult:
        """Resolve an interact action (pickup, use, open, pull, etc.)."""
        target_key = action.target_id
        interaction = action.interaction_type
        patches: list[StatePatch] = []
        description_parts: list[str] = []

        # Look up the object in inspectable_objects
        obj = self.inspectable_objects.get(target_key)
        if obj is None:
            for key, val in self.inspectable_objects.items():
                if val.get("object_id") == target_key or val.get("name", "").lower() == target_key.lower():
                    obj = val
                    target_key = key
                    break

        obj_name = obj.get("name", target_key) if obj else target_key

        if interaction == "pickup":
            # Check if there are discoverable contents from secrets
            items_found: list[str] = []
            if obj and "secrets" in obj:
                for secret_name, secret in obj["secrets"].items():
                    contents = secret.get("contents", [])
                    if contents:
                        # Check if this secret was discovered
                        flag_key = secret_name
                        if state.flags.get(flag_key, False):
                            items_found.extend(contents)

            if items_found:
                # Add items to actor's inventory
                actor = state.characters.get(actor_id) or state.npcs.get(actor_id)
                if actor:
                    current_inventory = list(actor.inventory) if actor.inventory else []
                    new_inventory = current_inventory + items_found
                    patches.append(StatePatch(
                        patch_type="inventory_add",
                        target_id=actor_id,
                        field="inventory",
                        old_value=current_inventory,
                        new_value=new_inventory,
                    ))

                    # Mark items as collected so they can't be picked up again
                    collected_flag = f"{target_key}_items_collected"
                    patches.append(StatePatch(
                        patch_type="flag",
                        target_id="flags",
                        field=collected_flag,
                        old_value=state.flags.get(collected_flag, False),
                        new_value=True,
                    ))

                    item_names = ", ".join(items_found)
                    description_parts.append(f"Picks up {item_names} from the {obj_name}.")
            else:
                description_parts.append(f"Reaches for items at the {obj_name} but finds nothing to take.")

        elif interaction == "use":
            # Generic use - check for effects in the object
            if obj and "secrets" in obj:
                for secret_name, secret in obj["secrets"].items():
                    effect = secret.get("effect")
                    if effect and state.flags.get(secret_name, False):
                        # Apply the effect as a flag
                        effect_flag = effect
                        if not state.flags.get(effect_flag, False):
                            patches.append(StatePatch(
                                patch_type="flag",
                                target_id="flags",
                                field=effect_flag,
                                old_value=False,
                                new_value=True,
                            ))
                            description_parts.append(f"Activates the {obj_name}. {secret.get('description', '')}")
                            break
            if not description_parts:
                description_parts.append(f"Attempts to use the {obj_name} but nothing happens.")

        elif interaction == "open":
            # Check if this is a door tile by target_id format "door:x,y"
            if target_key.startswith("door:"):
                door_result = self._handle_door_open(target_key, actor_id, state)
                if door_result:
                    return door_result
            description_parts.append(f"Opens the {obj_name}.")

        elif interaction == "close":
            # Check if this is a door tile by target_id format "door:x,y"
            if target_key.startswith("door:"):
                door_result = self._handle_door_close(target_key, actor_id, state)
                if door_result:
                    return door_result
            description_parts.append(f"Closes the {obj_name}.")

        elif interaction == "pull":
            description_parts.append(f"Pulls the {obj_name}.")

        elif interaction == "push":
            description_parts.append(f"Pushes the {obj_name}.")

        else:
            description_parts.append(f"Interacts with the {obj_name}.")

        return ResolutionResult(
            success=True,
            action_type=ActionType.INTERACT,
            dice_rolls=[],
            state_patches=patches,
            description=" ".join(description_parts),
        )

    def _parse_door_target(self, target_key: str) -> tuple[int, int] | None:
        """Parse a door target like 'door:5,7' into (x, y) coordinates."""
        if not target_key.startswith("door:"):
            return None
        coords = target_key[5:]  # Remove "door:" prefix
        try:
            parts = coords.split(",")
            if len(parts) == 2:
                return int(parts[0].strip()), int(parts[1].strip())
        except (ValueError, AttributeError):
            pass
        return None

    def _is_adjacent_to_actor(self, actor_id: str, x: int, y: int, state: GameState) -> bool:
        """Check if a position is adjacent to the actor."""
        actor = state.characters.get(actor_id) or state.npcs.get(actor_id)
        if not actor or not actor.position:
            return False
        dx = abs(actor.position.x - x)
        dy = abs(actor.position.y - y)
        return dx <= 1 and dy <= 1 and (dx + dy) > 0  # Adjacent but not same tile

    def _handle_door_open(
        self, target_key: str, actor_id: str, state: GameState
    ) -> ResolutionResult | None:
        """Handle opening a door at the specified coordinates."""
        coords = self._parse_door_target(target_key)
        if not coords:
            return None
        
        x, y = coords
        
        # Validate the dungeon map exists
        if state.dungeon_map is None:
            return ResolutionResult(
                success=False,
                action_type=ActionType.INTERACT,
                description="No dungeon map exists.",
            )
        
        # Validate coordinates are in bounds
        if not (0 <= x < state.dungeon_map.width and 0 <= y < state.dungeon_map.height):
            return ResolutionResult(
                success=False,
                action_type=ActionType.INTERACT,
                description=f"Door coordinates ({x},{y}) are out of bounds.",
            )
        
        tile = state.dungeon_map.tiles[y][x]
        
        # Check if it's actually a door
        if tile.terrain not in {TerrainType.DOOR, TerrainType.DOOR_LOCKED}:
            return ResolutionResult(
                success=False,
                action_type=ActionType.INTERACT,
                description=f"There is no door at ({x},{y}).",
            )
        
        # Check if actor is adjacent
        if not self._is_adjacent_to_actor(actor_id, x, y, state):
            return ResolutionResult(
                success=False,
                action_type=ActionType.INTERACT,
                description=f"Must be adjacent to the door to open it.",
            )
        
        # Check if already open
        if tile.door_open:
            return ResolutionResult(
                success=False,
                action_type=ActionType.INTERACT,
                description="The door is already open.",
            )
        
        # Check if locked
        if tile.terrain == TerrainType.DOOR_LOCKED:
            return ResolutionResult(
                success=False,
                action_type=ActionType.INTERACT,
                description="The door is locked. It must be unlocked first.",
            )
        
        # Open the door
        patches = [
            StatePatch(
                patch_type="door_open",
                target_id=f"tile:{x},{y}",
                field="door_open",
                old_value=False,
                new_value=True,
            )
        ]
        
        return ResolutionResult(
            success=True,
            action_type=ActionType.INTERACT,
            state_patches=patches,
            description=f"Opens the door at ({x},{y}).",
        )

    def _handle_door_close(
        self, target_key: str, actor_id: str, state: GameState
    ) -> ResolutionResult | None:
        """Handle closing a door at the specified coordinates."""
        coords = self._parse_door_target(target_key)
        if not coords:
            return None
        
        x, y = coords
        
        # Validate the dungeon map exists
        if state.dungeon_map is None:
            return ResolutionResult(
                success=False,
                action_type=ActionType.INTERACT,
                description="No dungeon map exists.",
            )
        
        # Validate coordinates are in bounds
        if not (0 <= x < state.dungeon_map.width and 0 <= y < state.dungeon_map.height):
            return ResolutionResult(
                success=False,
                action_type=ActionType.INTERACT,
                description=f"Door coordinates ({x},{y}) are out of bounds.",
            )
        
        tile = state.dungeon_map.tiles[y][x]
        
        # Check if it's actually a door
        if tile.terrain not in {TerrainType.DOOR, TerrainType.DOOR_LOCKED}:
            return ResolutionResult(
                success=False,
                action_type=ActionType.INTERACT,
                description=f"There is no door at ({x},{y}).",
            )
        
        # Check if actor is adjacent
        if not self._is_adjacent_to_actor(actor_id, x, y, state):
            return ResolutionResult(
                success=False,
                action_type=ActionType.INTERACT,
                description=f"Must be adjacent to the door to close it.",
            )
        
        # Check if already closed
        if not tile.door_open:
            return ResolutionResult(
                success=False,
                action_type=ActionType.INTERACT,
                description="The door is already closed.",
            )
        
        # Close the door
        patches = [
            StatePatch(
                patch_type="door_close",
                target_id=f"tile:{x},{y}",
                field="door_open",
                old_value=True,
                new_value=False,
            )
        ]
        
        return ResolutionResult(
            success=True,
            action_type=ActionType.INTERACT,
            state_patches=patches,
            description=f"Closes the door at ({x},{y}).",
        )

    def _parse_dice_notation(self, notation: str) -> tuple[int, str]:
        """Parse '2d8' into (count=2, die='d8'). Falls back to (1, notation)."""
        if "d" in notation:
            parts = notation.lower().split("d", 1)
            try:
                count = int(parts[0]) if parts[0] else 1
                die = f"d{parts[1]}"
                return count, die
            except (ValueError, IndexError):
                pass
        return 1, notation

    def _get_spell_info(self, spell_id: str) -> tuple[str, int, int, str]:
        """Returns (damage_die, die_count, modifier, spell_name) from rules or defaults."""
        if self.rules and spell_id:
            spell = self.rules.get_spell(spell_id)
            if spell:
                damage_die = DEFAULT_SPELL_DAMAGE_DIE
                die_count = DEFAULT_SPELL_DAMAGE_COUNT
                if spell.effect and spell.effect.damage_dice:
                    die_count, damage_die = self._parse_dice_notation(spell.effect.damage_dice)
                return damage_die, die_count, DEFAULT_SPELL_DAMAGE_MODIFIER, spell.name
        return DEFAULT_SPELL_DAMAGE_DIE, DEFAULT_SPELL_DAMAGE_COUNT, DEFAULT_SPELL_DAMAGE_MODIFIER, spell_id or "unknown"

    def _resolve_cast_spell(
        self, action: CastSpellBasicAction, actor_id: str, state: GameState
    ) -> ResolutionResult:
        dice_rolls: list[DiceRoll] = []
        patches: list[StatePatch] = []

        spell_attack = self.dice.roll_d20(DEFAULT_SPELL_ATTACK_MODIFIER)
        dice_rolls.append(spell_attack)

        damage_die, die_count, damage_mod, spell_name = self._get_spell_info(action.spell_id)

        hit = False
        damage = 0

        if action.target_id:
            target_ac = self._get_target_ac(action.target_id, state)
            hit = spell_attack.total >= target_ac

            if hit:
                spell_damage = self.dice.roll_damage(damage_die, die_count, damage_mod)
                dice_rolls.extend(spell_damage)
                damage = sum(r.total for r in spell_damage)

                self._apply_damage(action.target_id, damage, state, patches)

        return ResolutionResult(
            success=True,
            action_type=ActionType.CAST_SPELL_BASIC,
            dice_rolls=dice_rolls,
            state_patches=patches,
            hit=hit if action.target_id else None,
            damage=damage if hit else None,
            description=f"Casts {spell_name}"
            + (f", {'hits' if hit else 'misses'}" if action.target_id else "")
            + (f", dealing {damage} damage" if hit and damage else ""),
        )
