from __future__ import annotations

import json
import math
from typing import TYPE_CHECKING

from .registry import AgentTool, ToolParameter, ToolRegistry
from ..utils.line_of_sight import is_position_visible_to_players

if TYPE_CHECKING:
    from shared_schemas.state import GameState


def _parse_grid_pos(node_id: str) -> tuple[int, int] | None:
    """Parse a grid position into (x, y).
    
    Supports multiple formats:
    - "x,y" format (e.g., "5,15")
    - "A3" or "B12" grid notation (col, row)
    """
    if not node_id:
        return None
    
    # Try "x,y" format first
    if "," in node_id:
        parts = node_id.split(",")
        if len(parts) == 2:
            try:
                return int(parts[0].strip()), int(parts[1].strip())
            except ValueError:
                pass
    
    # Try "A3" grid notation
    if len(node_id) < 2:
        return None
    col_part = ""
    row_part = ""
    for ch in node_id:
        if ch.isalpha():
            col_part += ch
        elif ch.isdigit():
            row_part += ch
    if not col_part or not row_part:
        return None
    col = 0
    for ch in col_part.upper():
        col = col * 26 + (ord(ch) - ord("A"))
    return col, int(row_part)


def register_state_tools(
    registry: ToolRegistry,
    state: GameState | None,
    recent_messages: list | None = None,
) -> None:
    if state is None:
        return

    def _get_player_positions() -> list[tuple[int, int]]:
        """Get positions of all player characters."""
        positions = []
        for char in state.characters.values():
            if char.position:
                positions.append((char.position.x, char.position.y))
        return positions

    def get_visible_entities() -> str:
        """Return entities that are currently visible via line of sight.
        
        Player characters are always visible to each other.
        NPCs are only visible if at least one player has line of sight to them
        (walls block vision, regardless of whether the tile was previously explored).
        """
        entities = []
        
        # Get all player positions for LOS calculations
        player_positions = _get_player_positions()
        
        # Player characters are always visible to each other
        for cid, char in state.characters.items():
            entry: dict = {
                "id": cid,
                "name": char.name,
                "type": "character",
                "hp": char.hp,
                "max_hp": char.max_hp,
                "ac": char.ac,
                "alive": char.alive,
                "status_effects": char.status_effects,
            }
            if char.position:
                entry["x"] = char.position.x
                entry["y"] = char.position.y
                if char.position.node_id:
                    entry["position"] = char.position.node_id
            entities.append(entry)

        # NPCs are only visible if a player has line of sight to them
        for nid, npc in state.npcs.items():
            if npc.position:
                # Check line of sight from any player to this NPC
                if not is_position_visible_to_players(
                    state.dungeon_map,
                    npc.position.x,
                    npc.position.y,
                    player_positions,
                ):
                    continue  # Skip NPCs not in line of sight
            
            entry = {
                "id": nid,
                "name": npc.name,
                "type": "npc",
                "disposition": npc.disposition,
                "hp": npc.hp,
                "max_hp": npc.max_hp,
                "ac": npc.ac,
                "alive": npc.alive,
                "status_effects": npc.status_effects,
            }
            if npc.position:
                entry["x"] = npc.position.x
                entry["y"] = npc.position.y
                if npc.position.node_id:
                    entry["position"] = npc.position.node_id
            entities.append(entry)

        return json.dumps(entities, indent=2)

    registry.register(AgentTool(
        name="get_visible_entities",
        description="List characters and NPCs that are currently visible via line of sight. NPCs behind walls are NOT included even if the area was previously explored - you can only see enemies you currently have line of sight to. Returns HP, AC, position, and status effects for visible entities only.",
        parameters=[],
        handler=get_visible_entities,
    ))

    def calculate_distance(from_pos: str, to_pos: str) -> str:
        p1 = _parse_grid_pos(from_pos)
        p2 = _parse_grid_pos(to_pos)
        if p1 is None or p2 is None:
            return json.dumps({
                "from": from_pos,
                "to": to_pos,
                "error": "Could not parse positions. Expected format like '5,15' or 'A1'.",
            })
        dx = abs(p1[0] - p2[0])
        dy = abs(p1[1] - p2[1])
        # D&D uses 5ft grid squares; diagonal movement costs 5ft per square (simplified)
        grid_distance = max(dx, dy)
        feet = grid_distance * 5
        return json.dumps({
            "from": from_pos,
            "to": to_pos,
            "grid_squares": grid_distance,
            "feet": feet,
        })

    registry.register(AgentTool(
        name="calculate_distance",
        description="Calculate the grid distance in squares and feet between two positions. Supports 'x,y' format (e.g., '5,15') or grid notation (e.g., 'A1').",
        parameters=[
            ToolParameter(name="from_pos", type="string", description="Starting position (e.g., '5,15' or 'A1')"),
            ToolParameter(name="to_pos", type="string", description="Target position (e.g., '10,20' or 'C4')"),
        ],
        handler=calculate_distance,
    ))

    messages_list = recent_messages or []

    def get_recent_messages(channel: str = "all", count: int = 5) -> str:
        count = min(count, 10)
        filtered = messages_list
        if channel and channel != "all":
            filtered = [m for m in filtered if getattr(m, "channel", None) == channel]
        selected = filtered[-count:] if filtered else []
        result = []
        for msg in selected:
            entry = {
                "sender_id": getattr(msg, "sender_id", "unknown"),
                "channel": getattr(msg, "channel", "unknown"),
                "text": getattr(msg, "text", ""),
            }
            if hasattr(msg, "created_at"):
                entry["created_at"] = str(msg.created_at)
            result.append(entry)
        return json.dumps(result, indent=2)

    registry.register(AgentTool(
        name="get_recent_messages",
        description="Retrieve recent messages from a specific communication channel.",
        parameters=[
            ToolParameter(name="channel", type="string", description="Channel: 'in_character', 'table_talk', 'all'", required=False),
            ToolParameter(name="count", type="integer", description="Number of recent messages (max 10)", required=False),
        ],
        handler=get_recent_messages,
    ))
