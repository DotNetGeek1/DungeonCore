from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List

from shared_schemas.context import AgentContext, AgentIdentity, CommunicationBudget
from shared_schemas.enums import ActionType, ActorRole, Visibility
from shared_schemas.events import GameEvent
from shared_schemas.memory import MemoryEntry
from shared_schemas.messages import TableMessage
from shared_schemas.state import GameState

from .utils.line_of_sight import is_position_visible_to_players

if TYPE_CHECKING:
    from game_rules import RulesLoader


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for English text."""
    return max(1, len(text) // 4)


@dataclass
class SectionBudget:
    """Token budget and content for a single context section."""
    name: str
    priority: int  # higher = trimmed first under pressure
    max_tokens: int = 512
    content: str = ""

    @property
    def estimated_tokens(self) -> int:
        return _estimate_tokens(self.content)


@dataclass
class ContextBuilderConfig:
    max_recent_events: int = 10
    max_recent_messages: int = 10
    max_memories: int = 5
    default_max_messages: int = 3
    default_max_message_length: int = 500
    total_token_budget: int = 6000
    identity_tokens: int = 400
    situation_tokens: int = 600
    perception_tokens: int = 1200
    communication_tokens: int = 800
    memory_tokens: int = 600
    contract_tokens: int = 400


class ContextBuilder:
    def __init__(self, config: ContextBuilderConfig | None = None, rules: RulesLoader | None = None) -> None:
        self.config = config or ContextBuilderConfig()
        self.rules = rules

    def build_context(
        self,
        session_id: str,
        agent_id: str,
        actor_id: str,
        actor_name: str,
        role: ActorRole,
        goals: list[str],
        state: GameState,
        events: list[GameEvent] | None = None,
        messages: list[TableMessage] | None = None,
        memories: list[MemoryEntry] | None = None,
        allowed_actions: list[ActionType] | None = None,
        remaining_messages: int | None = None,
    ) -> AgentContext:
        identity = AgentIdentity(
            agent_id=agent_id,
            actor_id=actor_id,
            role=role,
            name=actor_name,
            goals=goals,
        )

        visible_state = self._filter_visible_state(state, actor_id, role)

        scene_summary = self._build_scene_summary(state, actor_id=actor_id)

        recent_events = self._filter_recent_events(
            events or [],
            actor_id,
            self.config.max_recent_events,
        )

        recent_messages = self._filter_visible_messages(
            messages or [],
            actor_id,
            role,
            self.config.max_recent_messages,
        )

        filtered_memories = self._filter_memories(
            memories or [],
            actor_id,
            self.config.max_memories,
        )

        if allowed_actions is None:
            allowed_actions = self._get_default_allowed_actions(role)

        comm_budget = CommunicationBudget(
            max_messages=self.config.default_max_messages,
            remaining_messages=remaining_messages if remaining_messages is not None else self.config.default_max_messages,
            max_message_length=self.config.default_max_message_length,
        )

        return AgentContext(
            session_id=session_id,
            identity=identity,
            scene_summary=scene_summary,
            visible_state=visible_state,
            recent_events=recent_events,
            recent_messages=recent_messages,
            memories=filtered_memories,
            allowed_actions=allowed_actions,
            communication_budget=comm_budget,
        )

    # ----- Structured prompt building (new) -----

    def build_structured_prompt(
        self,
        agent_ctx: AgentContext,
        actor_name: str,
        role: ActorRole,
        goals: list[str],
        personality_traits: list[str] | None = None,
    ) -> str:
        """Build a token-budgeted structured user prompt from priority sections."""
        sections = self._build_sections(agent_ctx, actor_name, role, goals, personality_traits)
        sections = self._trim_to_budget(sections)
        return "\n\n".join(
            f"=== {s.name.upper()} ===\n{s.content}"
            for s in sections
            if s.content.strip()
        )

    def _build_sections(
        self,
        ctx: AgentContext,
        actor_name: str,
        role: ActorRole,
        goals: list[str],
        personality_traits: list[str] | None = None,
    ) -> list[SectionBudget]:
        # Section 1: Identity (lowest priority to trim — always keep)
        identity_parts = [
            f"Name: {actor_name}",
            f"Role: {role}",
        ]
        if goals:
            identity_parts.append("Goals: " + "; ".join(goals))
        if personality_traits:
            identity_parts.append("Personality: " + ", ".join(personality_traits))

        identity = SectionBudget(
            name="Identity",
            priority=1,
            max_tokens=self.config.identity_tokens,
            content="\n".join(identity_parts),
        )

        # Section 2: Situation
        situation = SectionBudget(
            name="Situation",
            priority=2,
            max_tokens=self.config.situation_tokens,
            content=ctx.scene_summary,
        )

        # Section 3: Map (when available)
        map_content = self._build_map_section(ctx.visible_state, role, ctx.identity.actor_id)
        map_section = SectionBudget(
            name="Map",
            priority=3,
            max_tokens=800,
            content=map_content,
        )

        # Section 4: Perception (visible entities with distance info for the acting player)
        actor_pos = self._get_actor_position(ctx.visible_state, ctx.identity.actor_id)
        entity_lines: list[str] = []
        for cid, char in ctx.visible_state.characters.items():
            if char.position:
                pos = f"({char.position.x},{char.position.y})"
            else:
                pos_node = char.position.node_id if char.position else "?"
                pos = pos_node
            effects = ", ".join(char.status_effects) if char.status_effects else "none"
            entity_lines.append(
                f"- {char.name} ({cid}): HP {char.hp}/{char.max_hp}, AC {char.ac}, pos {pos}, status: {effects}"
            )

        # For NPCs, add distance from the acting player and action guidance
        for nid, npc in ctx.visible_state.npcs.items():
            if npc.position:
                pos = f"({npc.position.x},{npc.position.y})"
            else:
                pos_node = npc.position.node_id if npc.position else "?"
                pos = pos_node
            effects = ", ".join(npc.status_effects) if npc.status_effects else "none"

            # Calculate distance if we have both positions
            distance_info = ""
            if actor_pos and npc.position and npc.disposition == "hostile":
                dist = max(abs(npc.position.x - actor_pos[0]), abs(npc.position.y - actor_pos[1]))
                if dist == 1:
                    distance_info = f", DIST=1 (ADJACENT - use 'attack')"
                elif dist > 1:
                    steps_needed = dist - 1
                    distance_info = f", DIST={dist} (use 'move_and_attack', need {steps_needed} step(s) to reach)"

            entity_lines.append(
                f"- {npc.name} ({nid}): HP {npc.hp}/{npc.max_hp}, AC {npc.ac}, pos {pos}, {npc.disposition}{distance_info}, status: {effects}"
            )

        perception = SectionBudget(
            name="Perception",
            priority=4,
            max_tokens=self.config.perception_tokens,
            content="\n".join(entity_lines) if entity_lines else "No entities visible.",
        )

        # Section 5: Memory (trimmed before communication)
        mem_lines: list[str] = []
        for mem in ctx.memories[:self.config.max_memories]:
            mem_lines.append(f"- [{mem.memory_type}] {mem.text}")
        memory = SectionBudget(
            name="Memory",
            priority=5,
            max_tokens=self.config.memory_tokens,
            content="\n".join(mem_lines) if mem_lines else "No relevant memories.",
        )

        # Section 6: Communication (trimmed before contract)
        msg_lines: list[str] = []
        for msg in ctx.recent_messages[-self.config.max_recent_messages:]:
            msg_lines.append(f"[{msg.channel}] {msg.sender_id}: {msg.text}")
        communication = SectionBudget(
            name="Communication",
            priority=6,
            max_tokens=self.config.communication_tokens,
            content="\n".join(msg_lines) if msg_lines else "No recent messages.",
        )

        # Section 7: Contract (highest priority to trim — output schema)
        contract_parts = [
            f"Available actions: {', '.join(str(a) for a in ctx.allowed_actions)}",
            f"Communication budget: {ctx.communication_budget.remaining_messages} messages remaining",
        ]
        if ctx.visible_state.dungeon_map is not None:
            contract_parts.append(
                "Movement: specify paths as 'x,y' coordinate strings, e.g. ['3,4', '3,5', '4,5']"
            )
        contract = SectionBudget(
            name="Contract",
            priority=7,
            max_tokens=self.config.contract_tokens,
            content="\n".join(contract_parts),
        )

        sections = [identity, situation, perception, communication, memory, contract]
        if map_content.strip():
            sections.insert(2, map_section)
        return sections

    def _build_map_section(
        self,
        state: GameState,
        role: ActorRole,
        actor_id: str,
    ) -> str:
        """Build an ASCII map section for the agent context."""
        if state.dungeon_map is None:
            return ""

        dungeon_map = state.dungeon_map
        is_dm = role == ActorRole.DM

        TERRAIN_ASCII = {
            "floor": ".", "wall": "#", "door": "D", "door_locked": "L",
            "stairs_up": "U", "stairs_down": "V", "difficult": "~",
            "pit": "O", "water_deep": "W",
        }
        CONTENT_ASCII = {
            "empty": "", "tree": "T", "altar": "A", "treasure_chest": "$",
            "campfire": "f", "pillar": "P", "statue": "S", "barrel": "b",
            "table": "t", "trap": "!", "trap_hidden": "?", "torch": "i",
            "rubble": "r", "bookshelf": "B", "fountain": "F", "lever": "l",
        }

        # Collect player positions for LOS calculations
        player_positions: list[tuple[int, int]] = []
        actor_positions: dict[tuple[int, int], str] = {}
        for cid, char in state.characters.items():
            if char.position:
                label = "Y" if cid == actor_id else char.name[0].upper()
                actor_positions[(char.position.x, char.position.y)] = label
                player_positions.append((char.position.x, char.position.y))
        
        # Only show NPCs that players have line of sight to
        for nid, npc in state.npcs.items():
            if npc.position:
                x, y = npc.position.x, npc.position.y
                # DM sees everything; players only see NPCs in their line of sight
                if is_dm or is_position_visible_to_players(
                    dungeon_map, x, y, player_positions
                ):
                    actor_positions[(x, y)] = npc.name[0].upper()

        lines: list[str] = [f"Dungeon Map: {dungeon_map.name} ({dungeon_map.width}x{dungeon_map.height})"]

        for y in range(dungeon_map.height):
            row = f"{y:2d}|"
            for x in range(dungeon_map.width):
                tile = dungeon_map.tiles[y][x]
                if not tile.revealed and not is_dm:
                    # Unrevealed tiles shown as '?' to indicate unknown/blocked
                    row += "?"
                    continue
                if (x, y) in actor_positions:
                    row += actor_positions[(x, y)]
                    continue
                content_char = CONTENT_ASCII.get(tile.content, "")
                if content_char and (tile.content != "trap_hidden" or is_dm):
                    row += content_char
                else:
                    terrain = tile.terrain
                    # Open doors should show as walkable floor, closed doors as 'D'
                    if terrain in ("door", "door_locked") and tile.door_open:
                        row += "."  # Open door = walkable
                    else:
                        row += TERRAIN_ASCII.get(terrain, ".")
            lines.append(row)

        lines.append("   " + "".join(str(x % 10) for x in range(dungeon_map.width)))
        lines.append("")
        lines.append("LEGEND: Y=you  #=wall(BLOCKED)  .=floor(OK)  D=CLOSED door(MUST OPEN)  L=locked door  ~=difficult(OK)  ?=unexplored(BLOCKED)")
        lines.append("MOVEMENT: Each step in movement_path must be ADJACENT (1 tile away). You cannot skip tiles!")
        lines.append("DOORS: To open a closed door at (x,y), use: {\"type\": \"interact\", \"target_id\": \"door:x,y\", \"interaction_type\": \"open\"}")
        return "\n".join(lines)

    def _trim_to_budget(self, sections: list[SectionBudget]) -> list[SectionBudget]:
        """Trim sections by priority (highest-priority-number first) until total fits."""
        total = sum(s.estimated_tokens for s in sections)
        if total <= self.config.total_token_budget:
            return sections

        by_priority = sorted(sections, key=lambda s: s.priority, reverse=True)
        for section in by_priority:
            if total <= self.config.total_token_budget:
                break
            excess = total - self.config.total_token_budget
            tokens_to_trim = min(excess, max(0, section.estimated_tokens - 50))
            if tokens_to_trim > 0:
                chars_to_trim = tokens_to_trim * 4
                section.content = section.content[:len(section.content) - chars_to_trim].rstrip()
                total = sum(s.estimated_tokens for s in sections)

        return sections

    # ----- Existing methods preserved -----

    def _filter_visible_state(
        self,
        state: GameState,
        actor_id: str,
        role: ActorRole,
    ) -> GameState:
        is_dm = role == ActorRole.DM

        # Collect all player positions for line-of-sight calculations
        player_positions: list[tuple[int, int]] = []
        if not is_dm:
            for char in state.characters.values():
                if char.position:
                    player_positions.append((char.position.x, char.position.y))

        def _has_line_of_sight_to(pos: object) -> bool:
            """Returns True if any player has line of sight to this position."""
            if state.dungeon_map is None or is_dm:
                return True
            if pos is None:
                return True  # no position info — show it
            px = getattr(pos, "x", None)
            py = getattr(pos, "y", None)
            if px is None or py is None:
                return True  # no coordinates — show it
            return is_position_visible_to_players(
                state.dungeon_map, px, py, player_positions
            )

        visible_characters = {}
        for cid, char in state.characters.items():
            # Always show self
            if cid == actor_id:
                visible_characters[cid] = char
                continue
            # Visibility scope check
            if char.visibility_scope.visibility not in (Visibility.PUBLIC,) and actor_id not in char.visibility_scope.recipient_ids:
                continue
            # Players are always visible to each other (party awareness)
            visible_characters[cid] = char

        visible_npcs = {}
        for nid, npc in state.npcs.items():
            # Visibility scope check
            if npc.visibility_scope.visibility not in (Visibility.PUBLIC,) and nid != actor_id and actor_id not in npc.visibility_scope.recipient_ids:
                continue
            # Line of sight: only show NPCs that players can currently see
            if not _has_line_of_sight_to(npc.position):
                continue
            visible_npcs[nid] = npc

        return state.model_copy(
            update={
                "characters": visible_characters,
                "npcs": visible_npcs,
            }
        )

    def _build_scene_summary(self, state: GameState, actor_id: str | None = None) -> str:
        scene = state.scene
        turn = state.turn

        parts = [
            f"Scene: {scene.name}",
            f"Summary: {scene.summary}",
            f"Turn {turn.turn_number}, Round {turn.round_number}",
            f"Phase: {scene.phase}",
        ]

        if scene.active_actor_id:
            parts.append(f"Active actor: {scene.active_actor_id}")

        if actor_id and self.rules:
            actor = state.characters.get(actor_id) or state.npcs.get(actor_id)
            if actor:
                parts.append(self._build_equipment_summary(actor))

        return "\n".join(parts)

    def _build_equipment_summary(self, actor: object) -> str:
        if not self.rules:
            return ""

        lines = ["Equipment:"]
        inventory = getattr(actor, "inventory", [])
        for item_id in inventory:
            weapon = self.rules.get_weapon(item_id)
            if weapon:
                props = ", ".join(weapon.properties) if weapon.properties else ""
                lines.append(f"  - {weapon.name}: {weapon.damage_dice} {weapon.damage_type}{' (' + props + ')' if props else ''}")
                continue
            armor = self.rules.get_armor(item_id)
            if armor:
                lines.append(f"  - {armor.name}: AC {armor.base_ac} ({armor.category})")
                continue
            lines.append(f"  - {item_id}")

        spell_slots = getattr(actor, "spell_slots", {})
        if spell_slots:
            slots_str = ", ".join(f"L{k}: {v}" for k, v in spell_slots.items())
            lines.append(f"Spell slots: {slots_str}")

        return "\n".join(lines) if len(lines) > 1 else ""

    def _filter_recent_events(
        self,
        events: list[GameEvent],
        actor_id: str,
        max_count: int,
    ) -> list[GameEvent]:
        return events[-max_count:] if events else []

    def _filter_visible_messages(
        self,
        messages: list[TableMessage],
        actor_id: str,
        role: ActorRole,
        max_count: int,
    ) -> list[TableMessage]:
        visible = []
        for msg in messages:
            if msg.sender_id == actor_id:
                visible.append(msg)
            elif msg.visibility == Visibility.PUBLIC:
                visible.append(msg)
            elif msg.visibility == Visibility.PARTY and role == ActorRole.PLAYER:
                visible.append(msg)
            elif actor_id in msg.recipient_ids:
                visible.append(msg)

        return visible[-max_count:] if visible else []

    def _filter_memories(
        self,
        memories: list[MemoryEntry],
        actor_id: str,
        max_count: int,
    ) -> list[MemoryEntry]:
        actor_memories = [m for m in memories if m.actor_id == actor_id]

        sorted_memories = sorted(
            actor_memories,
            key=lambda m: (m.importance, m.created_at_turn),
            reverse=True,
        )

        return sorted_memories[:max_count]

    def _get_actor_position(self, state: GameState, actor_id: str) -> tuple[int, int] | None:
        """Get the (x, y) position of the actor if available."""
        if actor_id in state.characters:
            pos = state.characters[actor_id].position
            if pos and hasattr(pos, "x") and hasattr(pos, "y"):
                return (pos.x, pos.y)
        if actor_id in state.npcs:
            pos = state.npcs[actor_id].position
            if pos and hasattr(pos, "x") and hasattr(pos, "y"):
                return (pos.x, pos.y)
        return None

    def _get_default_allowed_actions(self, role: ActorRole) -> list[ActionType]:
        if role == ActorRole.PLAYER:
            return [
                ActionType.ATTACK,
                ActionType.MOVE,
                ActionType.MOVE_AND_ATTACK,
                ActionType.DEFEND,
                ActionType.INSPECT,
                ActionType.INTERACT,
                ActionType.CAST_SPELL_BASIC,
            ]
        elif role == ActorRole.DM:
            return []
        else:
            return [
                ActionType.ATTACK,
                ActionType.MOVE,
                ActionType.DEFEND,
            ]


def get_context_builder(
    config: ContextBuilderConfig | None = None,
    rules: RulesLoader | None = None,
) -> ContextBuilder:
    return ContextBuilder(config, rules=rules)
