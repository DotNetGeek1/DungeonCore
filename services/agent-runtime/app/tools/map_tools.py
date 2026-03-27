from __future__ import annotations

import json
import random
from typing import Any

from shared_schemas.state import (
    DungeonMap,
    GameState,
    MapTile,
    NpcState,
    Position,
    TerrainType,
    TileContent,
    VisibilityScope,
)
from shared_schemas.enums import ActorRole, Visibility

from .registry import AgentTool, ToolParameter, ToolRegistry

TERRAIN_ASCII = {
    TerrainType.FLOOR: ".",
    TerrainType.WALL: "#",
    TerrainType.DOOR: "D",
    TerrainType.DOOR_LOCKED: "L",
    TerrainType.STAIRS_UP: "U",
    TerrainType.STAIRS_DOWN: "V",
    TerrainType.DIFFICULT: "~",
    TerrainType.PIT: "O",
    TerrainType.WATER_DEEP: "W",
}

CONTENT_ASCII = {
    TileContent.EMPTY: "",
    TileContent.TREE: "T",
    TileContent.ALTAR: "A",
    TileContent.TREASURE_CHEST: "$",
    TileContent.CAMPFIRE: "f",
    TileContent.PILLAR: "P",
    TileContent.STATUE: "S",
    TileContent.BARREL: "b",
    TileContent.TABLE: "t",
    TileContent.TRAP: "!",
    TileContent.TRAP_HIDDEN: "?",
    TileContent.TORCH: "i",
    TileContent.RUBBLE: "r",
    TileContent.BOOKSHELF: "B",
    TileContent.FOUNTAIN: "F",
    TileContent.LEVER: "l",
}


def render_map_ascii(
    dungeon_map: DungeonMap,
    actors: dict[str, tuple[int, int, str]] | None = None,
    show_all: bool = False,
) -> str:
    """
    Render the map as an ASCII grid.

    Args:
        dungeon_map: The dungeon map to render.
        actors: Dict of actor_id -> (x, y, label) for overlay markers.
        show_all: If True, show unrevealed tiles; otherwise show as ' '.

    Returns:
        Multi-line ASCII string with coordinate axis labels.
    """
    lines: list[str] = []

    # X-axis header (show every 5 cols)
    col_header = "   "
    for x in range(dungeon_map.width):
        if x % 5 == 0:
            col_header += str(x).ljust(5)
    lines.append(col_header)

    actor_positions: dict[tuple[int, int], str] = {}
    if actors:
        for actor_id, (ax, ay, label) in actors.items():
            actor_positions[(ax, ay)] = label[:1].upper()

    for y in range(dungeon_map.height):
        row_str = f"{y:2d} "
        for x in range(dungeon_map.width):
            tile = dungeon_map.tiles[y][x]

            if not tile.revealed and not show_all:
                row_str += " "
                continue

            # Actor marker takes priority
            if (x, y) in actor_positions:
                row_str += actor_positions[(x, y)]
                continue

            content_char = CONTENT_ASCII.get(tile.content, "")
            if content_char:
                row_str += content_char
            else:
                row_str += TERRAIN_ASCII.get(tile.terrain, ".")

        lines.append(row_str)

    legend = (
        "Legend: .=floor #=wall D=door L=locked U/V=stairs ~=difficult "
        "O=pit W=water T=tree A=altar $=treasure P=pillar f=campfire "
        "!=trap ?=hidden_trap"
    )
    lines.append(legend)
    return "\n".join(lines)


def _make_place_tiles_handler(state: GameState) -> Any:
    def handle_place_tiles(
        changes: str,
        reveal: bool = True,
    ) -> str:
        """
        Apply tile changes to the dungeon map.

        Args:
            changes: JSON array of change objects with fields:
                     x, y, terrain (optional), content (optional),
                     label (optional), elevation (optional)
            reveal: If True, mark changed tiles as revealed.
        """
        if state.dungeon_map is None:
            return json.dumps({"error": "No dungeon map exists in current game state"})

        try:
            change_list = json.loads(changes) if isinstance(changes, str) else changes
        except (json.JSONDecodeError, TypeError) as e:
            return json.dumps({"error": f"Invalid changes JSON: {e}"})

        if not isinstance(change_list, list):
            return json.dumps({"error": "'changes' must be a JSON array"})

        dungeon_map = state.dungeon_map
        applied = 0
        errors: list[str] = []

        for item in change_list:
            try:
                x = int(item["x"])
                y = int(item["y"])
            except (KeyError, ValueError, TypeError) as e:
                errors.append(f"Invalid coordinates in item: {e}")
                continue

            if not (0 <= x < dungeon_map.width and 0 <= y < dungeon_map.height):
                errors.append(f"Coordinates ({x},{y}) out of bounds")
                continue

            tile = dungeon_map.tiles[y][x]
            tile_data: dict[str, Any] = tile.model_dump()

            if "terrain" in item and item["terrain"] is not None:
                try:
                    new_terrain = TerrainType(item["terrain"])
                    
                    # Prevent placing doors adjacent to existing doors
                    if new_terrain in (TerrainType.DOOR, TerrainType.DOOR_LOCKED):
                        has_adjacent_door = False
                        for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                            adj_x, adj_y = x + dx, y + dy
                            if 0 <= adj_x < dungeon_map.width and 0 <= adj_y < dungeon_map.height:
                                adj_tile = dungeon_map.tiles[adj_y][adj_x]
                                if adj_tile.terrain in (TerrainType.DOOR, TerrainType.DOOR_LOCKED):
                                    has_adjacent_door = True
                                    break
                        if has_adjacent_door:
                            errors.append(f"Cannot place door at ({x},{y}) - adjacent to existing door. Doors should not be back-to-back.")
                            continue
                    
                    tile_data["terrain"] = new_terrain
                except ValueError:
                    errors.append(f"Unknown terrain '{item['terrain']}' at ({x},{y})")
                    continue

            if "content" in item and item["content"] is not None:
                try:
                    tile_data["content"] = TileContent(item["content"])
                except ValueError:
                    errors.append(f"Unknown content '{item['content']}' at ({x},{y})")
                    continue

            if "label" in item:
                tile_data["label"] = item["label"]

            if "elevation" in item and item["elevation"] is not None:
                tile_data["elevation"] = int(item["elevation"])

            if reveal:
                tile_data["revealed"] = True

            dungeon_map.tiles[y][x] = MapTile(**tile_data)
            applied += 1

        result: dict[str, Any] = {"applied": applied}
        if errors:
            result["warnings"] = errors
        return json.dumps(result)

    return handle_place_tiles


def _make_reveal_area_handler(state: GameState) -> Any:
    def handle_reveal_area(
        x1: int,
        y1: int,
        x2: int,
        y2: int,
    ) -> str:
        """
        Mark a rectangular region of tiles as revealed (fog of war).

        Args:
            x1: Left column (inclusive).
            y1: Top row (inclusive).
            x2: Right column (inclusive).
            y2: Bottom row (inclusive).
        """
        if state.dungeon_map is None:
            return json.dumps({"error": "No dungeon map exists in current game state"})

        dungeon_map = state.dungeon_map
        revealed = 0

        x_min, x_max = min(x1, x2), max(x1, x2)
        y_min, y_max = min(y1, y2), max(y1, y2)

        for y in range(y_min, y_max + 1):
            for x in range(x_min, x_max + 1):
                if 0 <= y < dungeon_map.height and 0 <= x < dungeon_map.width:
                    tile = dungeon_map.tiles[y][x]
                    if not tile.revealed:
                        tile_data = tile.model_dump()
                        tile_data["revealed"] = True
                        dungeon_map.tiles[y][x] = MapTile(**tile_data)
                        revealed += 1

        return json.dumps({"revealed": revealed, "region": f"({x_min},{y_min})-({x_max},{y_max})"})

    return handle_reveal_area


def _make_get_map_summary_handler(state: GameState) -> Any:
    def handle_get_map_summary(show_all: bool = False) -> str:
        """
        Get an ASCII text summary of the current dungeon map.

        Args:
            show_all: If True (DM view), show the full map including unrevealed tiles.
        """
        if state.dungeon_map is None:
            return json.dumps({"error": "No dungeon map exists in current game state"})

        actors: dict[str, tuple[int, int, str]] = {}
        for cid, char in state.characters.items():
            if char.position:
                actors[cid] = (char.position.x, char.position.y, char.name[0])
        for nid, npc in state.npcs.items():
            if npc.position:
                actors[nid] = (npc.position.x, npc.position.y, npc.name[0])

        ascii_map = render_map_ascii(state.dungeon_map, actors=actors, show_all=show_all)
        return json.dumps({
            "map_name": state.dungeon_map.name,
            "width": state.dungeon_map.width,
            "height": state.dungeon_map.height,
            "ascii_map": ascii_map,
        })

    return handle_get_map_summary


ROOM_STYLES = {
    "rectangular": "Standard rectangular room with corners",
    "irregular": "Room with alcoves and irregular shape",
    "circular": "Round chamber (approximated on grid)",
    "corridor": "Long narrow passage",
    "chamber": "Large open chamber for boss fights",
}

ROOM_THEMES = {
    "empty": {"content_density": 0.0, "contents": []},
    "storage": {"content_density": 0.4, "contents": [TileContent.BARREL, TileContent.TABLE, TileContent.BOOKSHELF]},
    "shrine": {"content_density": 0.3, "contents": [TileContent.ALTAR, TileContent.STATUE, TileContent.TORCH]},
    "treasure": {"content_density": 0.2, "contents": [TileContent.TREASURE_CHEST, TileContent.PILLAR]},
    "trap_room": {"content_density": 0.3, "contents": [TileContent.TRAP_HIDDEN, TileContent.RUBBLE]},
    "living_quarters": {"content_density": 0.3, "contents": [TileContent.CAMPFIRE, TileContent.TABLE, TileContent.BARREL]},
    "library": {"content_density": 0.5, "contents": [TileContent.BOOKSHELF, TileContent.TABLE, TileContent.TORCH]},
    "fountain_room": {"content_density": 0.2, "contents": [TileContent.FOUNTAIN, TileContent.PILLAR, TileContent.STATUE]},
}


def _make_init_map_handler(state: GameState) -> Any:
    def handle_init_map(
        name: str,
        width: int,
        height: int,
        default_terrain: str = "wall",
    ) -> str:
        """
        Initialize a new empty dungeon map with the specified dimensions.

        Args:
            name: Name of the dungeon map.
            width: Width of the map in tiles.
            height: Height of the map in tiles.
            default_terrain: Default terrain type for all tiles (default: wall).
        """
        if width < 10 or width > 100:
            return json.dumps({"error": "Width must be between 10 and 100"})
        if height < 10 or height > 100:
            return json.dumps({"error": "Height must be between 10 and 100"})

        try:
            terrain = TerrainType(default_terrain)
        except ValueError:
            terrain = TerrainType.WALL

        tiles = []
        for y in range(height):
            row = []
            for x in range(width):
                row.append(MapTile(terrain=terrain, content=TileContent.EMPTY, revealed=False))
            tiles.append(row)

        new_map = DungeonMap(
            name=name,
            width=width,
            height=height,
            tiles=tiles,
            default_terrain=terrain,
        )
        state.dungeon_map = new_map
        
        # Debug: verify the state was modified
        print(f"[init_map] Created map '{name}' ({width}x{height}), state.dungeon_map is now: {state.dungeon_map is not None}")

        return json.dumps({
            "success": True,
            "map_name": name,
            "width": width,
            "height": height,
            "message": f"Created new {width}x{height} dungeon map '{name}'",
        })

    return handle_init_map


def _make_generate_room_handler(state: GameState) -> Any:
    def handle_generate_room(
        room_id: str,
        x: int,
        y: int,
        width: int,
        height: int,
        style: str = "rectangular",
        revealed: bool = False,
        door_positions: str = "[]",
    ) -> str:
        """
        Generate a room at the specified position with walls and floor.

        Args:
            room_id: Unique identifier for this room (used in labels).
            x: Left edge x coordinate.
            y: Top edge y coordinate.
            width: Room width in tiles.
            height: Room height in tiles.
            style: Room style - 'rectangular', 'irregular', 'circular', 'corridor', 'chamber'.
            revealed: Whether the room starts revealed to players.
            door_positions: JSON array of door positions relative to room, e.g. [{"side": "north", "offset": 2}].
        """
        if state.dungeon_map is None:
            return json.dumps({"error": "No dungeon map exists. Call init_map first."})

        dungeon_map = state.dungeon_map

        if x < 0 or y < 0 or x + width > dungeon_map.width or y + height > dungeon_map.height:
            return json.dumps({"error": f"Room bounds ({x},{y}) to ({x+width-1},{y+height-1}) exceed map dimensions"})

        try:
            doors = json.loads(door_positions) if isinstance(door_positions, str) else door_positions
        except json.JSONDecodeError:
            doors = []

        tiles_placed = 0

        for ry in range(height):
            for rx in range(width):
                map_x = x + rx
                map_y = y + ry

                is_wall = (rx == 0 or rx == width - 1 or ry == 0 or ry == height - 1)

                if style == "circular":
                    cx, cy = width / 2, height / 2
                    dx, dy = rx - cx + 0.5, ry - cy + 0.5
                    dist = (dx * dx / (cx * cx) + dy * dy / (cy * cy))
                    if dist > 1.0:
                        continue
                    is_wall = dist > 0.7

                if style == "irregular" and not is_wall:
                    pass

                terrain = TerrainType.WALL if is_wall else TerrainType.FLOOR
                label = f"{room_id}-wall" if is_wall else f"{room_id}-floor"

                dungeon_map.tiles[map_y][map_x] = MapTile(
                    terrain=terrain,
                    content=TileContent.EMPTY,
                    revealed=revealed,
                    label=label,
                )
                tiles_placed += 1

        doors_placed = 0
        for door_spec in doors:
            side = door_spec.get("side", "north")
            offset = door_spec.get("offset", 1)
            locked = door_spec.get("locked", False)

            if side == "north":
                door_x, door_y = x + offset, y
            elif side == "south":
                door_x, door_y = x + offset, y + height - 1
            elif side == "west":
                door_x, door_y = x, y + offset
            elif side == "east":
                door_x, door_y = x + width - 1, y + offset
            else:
                continue

            if 0 <= door_x < dungeon_map.width and 0 <= door_y < dungeon_map.height:
                # Check if there's already a door at this position or adjacent
                existing_tile = dungeon_map.tiles[door_y][door_x]
                if existing_tile.terrain in (TerrainType.DOOR, TerrainType.DOOR_LOCKED):
                    continue  # Don't place duplicate door
                
                # Check adjacent tiles for existing doors to avoid double doors
                has_adjacent_door = False
                for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                    adj_x, adj_y = door_x + dx, door_y + dy
                    if 0 <= adj_x < dungeon_map.width and 0 <= adj_y < dungeon_map.height:
                        adj_tile = dungeon_map.tiles[adj_y][adj_x]
                        if adj_tile.terrain in (TerrainType.DOOR, TerrainType.DOOR_LOCKED):
                            has_adjacent_door = True
                            break
                
                if has_adjacent_door:
                    continue  # Don't place door adjacent to existing door
                
                dungeon_map.tiles[door_y][door_x] = MapTile(
                    terrain=TerrainType.DOOR_LOCKED if locked else TerrainType.DOOR,
                    content=TileContent.EMPTY,
                    revealed=revealed,
                    label=f"{room_id}-door",
                )
                doors_placed += 1

        return json.dumps({
            "success": True,
            "room_id": room_id,
            "position": f"({x},{y})",
            "size": f"{width}x{height}",
            "style": style,
            "tiles_placed": tiles_placed,
            "doors_placed": doors_placed,
        })

    return handle_generate_room


def _make_connect_rooms_handler(state: GameState) -> Any:
    def handle_connect_rooms(
        from_x: int,
        from_y: int,
        to_x: int,
        to_y: int,
        corridor_width: int = 1,
        style: str = "straight",
        revealed: bool = False,
    ) -> str:
        """
        Create a corridor connecting two points.

        Args:
            from_x: Starting x coordinate.
            from_y: Starting y coordinate.
            to_x: Ending x coordinate.
            to_y: Ending y coordinate.
            corridor_width: Width of the corridor (default 1).
            style: 'straight' (L-shaped) or 'winding' (random path).
            revealed: Whether the corridor starts revealed.
        """
        if state.dungeon_map is None:
            return json.dumps({"error": "No dungeon map exists"})

        dungeon_map = state.dungeon_map
        tiles_placed = 0

        if style == "winding":
            cx, cy = from_x, from_y
            while cx != to_x or cy != to_y:
                if random.random() < 0.5 and cx != to_x:
                    cx += 1 if to_x > cx else -1
                elif cy != to_y:
                    cy += 1 if to_y > cy else -1
                elif cx != to_x:
                    cx += 1 if to_x > cx else -1

                if 0 <= cx < dungeon_map.width and 0 <= cy < dungeon_map.height:
                    for w in range(corridor_width):
                        wx = cx
                        wy = cy + w if cy == from_y or cy == to_y else cy
                        if 0 <= wx < dungeon_map.width and 0 <= wy < dungeon_map.height:
                            tile = dungeon_map.tiles[wy][wx]
                            if tile.terrain == TerrainType.WALL:
                                dungeon_map.tiles[wy][wx] = MapTile(
                                    terrain=TerrainType.FLOOR,
                                    content=TileContent.EMPTY,
                                    revealed=revealed,
                                    label="corridor",
                                )
                                tiles_placed += 1
        else:
            for x in range(min(from_x, to_x), max(from_x, to_x) + 1):
                for w in range(corridor_width):
                    y = from_y + w
                    if 0 <= x < dungeon_map.width and 0 <= y < dungeon_map.height:
                        tile = dungeon_map.tiles[y][x]
                        if tile.terrain == TerrainType.WALL:
                            dungeon_map.tiles[y][x] = MapTile(
                                terrain=TerrainType.FLOOR,
                                content=TileContent.EMPTY,
                                revealed=revealed,
                                label="corridor",
                            )
                            tiles_placed += 1

            for y in range(min(from_y, to_y), max(from_y, to_y) + 1):
                for w in range(corridor_width):
                    x = to_x + w
                    if 0 <= x < dungeon_map.width and 0 <= y < dungeon_map.height:
                        tile = dungeon_map.tiles[y][x]
                        if tile.terrain == TerrainType.WALL:
                            dungeon_map.tiles[y][x] = MapTile(
                                terrain=TerrainType.FLOOR,
                                content=TileContent.EMPTY,
                                revealed=revealed,
                                label="corridor",
                            )
                            tiles_placed += 1

        return json.dumps({
            "success": True,
            "from": f"({from_x},{from_y})",
            "to": f"({to_x},{to_y})",
            "style": style,
            "tiles_placed": tiles_placed,
        })

    return handle_connect_rooms


def _make_populate_room_handler(state: GameState) -> Any:
    def handle_populate_room(
        x: int,
        y: int,
        width: int,
        height: int,
        theme: str = "empty",
        density: float = 0.3,
        seed: int | None = None,
    ) -> str:
        """
        Populate a room area with themed content.

        Args:
            x: Left edge of the room interior.
            y: Top edge of the room interior.
            width: Width of the interior area.
            height: Height of the interior area.
            theme: Room theme - 'empty', 'storage', 'shrine', 'treasure', 'trap_room', 'living_quarters', 'library', 'fountain_room'.
            density: Probability of placing content on each floor tile (0.0 to 1.0).
            seed: Random seed for reproducible placement.
        """
        if state.dungeon_map is None:
            return json.dumps({"error": "No dungeon map exists"})

        if seed is not None:
            random.seed(seed)

        theme_config = ROOM_THEMES.get(theme, ROOM_THEMES["empty"])
        contents = theme_config.get("contents", [])
        actual_density = min(density, theme_config.get("content_density", 0.3))

        if not contents:
            return json.dumps({
                "success": True,
                "theme": theme,
                "items_placed": 0,
                "message": "Theme has no contents to place",
            })

        dungeon_map = state.dungeon_map
        items_placed = 0

        interior_x = x + 1
        interior_y = y + 1
        interior_width = max(1, width - 2)
        interior_height = max(1, height - 2)

        for ry in range(interior_height):
            for rx in range(interior_width):
                map_x = interior_x + rx
                map_y = interior_y + ry

                if not (0 <= map_x < dungeon_map.width and 0 <= map_y < dungeon_map.height):
                    continue

                tile = dungeon_map.tiles[map_y][map_x]
                if tile.terrain != TerrainType.FLOOR or tile.content != TileContent.EMPTY:
                    continue

                if random.random() < actual_density:
                    content = random.choice(contents)
                    dungeon_map.tiles[map_y][map_x] = MapTile(
                        terrain=tile.terrain,
                        content=content,
                        revealed=tile.revealed,
                        label=tile.label,
                    )
                    items_placed += 1

        return json.dumps({
            "success": True,
            "theme": theme,
            "items_placed": items_placed,
            "area": f"({interior_x},{interior_y}) to ({interior_x + interior_width - 1},{interior_y + interior_height - 1})",
        })

    return handle_populate_room


def _make_spawn_enemies_handler(state: GameState):
    """Create a handler to spawn enemies on the map."""

    ENEMY_TEMPLATES = {
        "goblin": {
            "base_name": "Goblin",
            "role": ActorRole.ENEMY,
            "hp": 7,
            "max_hp": 7,
            "ac": 12,
            "initiative": 1,
            "inventory": ["scimitar", "shortbow"],
            "disposition": "hostile",
            "behavior_tag": "melee_aggressive",
        },
        "goblin_shaman": {
            "base_name": "Goblin Shaman",
            "role": ActorRole.ENEMY,
            "hp": 15,
            "max_hp": 15,
            "ac": 11,
            "initiative": 3,
            "inventory": ["quarterstaff"],
            "spell_slots": {"1": 2, "2": 1},
            "disposition": "hostile",
            "behavior_tag": "caster_support",
        },
        "skeleton": {
            "base_name": "Skeleton",
            "role": ActorRole.ENEMY,
            "hp": 13,
            "max_hp": 13,
            "ac": 13,
            "initiative": 2,
            "inventory": ["shortsword", "shortbow"],
            "disposition": "hostile",
            "behavior_tag": "melee_aggressive",
        },
        "zombie": {
            "base_name": "Zombie",
            "role": ActorRole.ENEMY,
            "hp": 22,
            "max_hp": 22,
            "ac": 8,
            "initiative": -2,
            "inventory": [],
            "disposition": "hostile",
            "behavior_tag": "melee_slow",
        },
        "bandit": {
            "base_name": "Bandit",
            "role": ActorRole.ENEMY,
            "hp": 11,
            "max_hp": 11,
            "ac": 12,
            "initiative": 1,
            "inventory": ["scimitar", "light_crossbow"],
            "disposition": "hostile",
            "behavior_tag": "ranged_opportunist",
        },
        "cultist": {
            "base_name": "Cultist",
            "role": ActorRole.ENEMY,
            "hp": 9,
            "max_hp": 9,
            "ac": 12,
            "initiative": 0,
            "inventory": ["scimitar"],
            "disposition": "hostile",
            "behavior_tag": "melee_aggressive",
        },
        "giant_spider": {
            "base_name": "Giant Spider",
            "role": ActorRole.ENEMY,
            "hp": 26,
            "max_hp": 26,
            "ac": 14,
            "initiative": 3,
            "inventory": [],
            "disposition": "hostile",
            "behavior_tag": "ambush_predator",
        },
        "wolf": {
            "base_name": "Wolf",
            "role": ActorRole.ENEMY,
            "hp": 11,
            "max_hp": 11,
            "ac": 13,
            "initiative": 2,
            "inventory": [],
            "disposition": "hostile",
            "behavior_tag": "pack_tactics",
        },
    }

    def handle_spawn_enemies(
        enemy_type: str,
        count: int = 1,
        x: int | None = None,
        y: int | None = None,
        room_x: int | None = None,
        room_y: int | None = None,
        room_width: int | None = None,
        room_height: int | None = None,
        name_prefix: str | None = None,
        **kwargs,
    ) -> str:
        enemy_type_lower = enemy_type.lower().replace(" ", "_")
        
        if enemy_type_lower not in ENEMY_TEMPLATES:
            return json.dumps({
                "success": False,
                "error": f"Unknown enemy type: {enemy_type}. Available: {', '.join(ENEMY_TEMPLATES.keys())}",
            })

        template = ENEMY_TEMPLATES[enemy_type_lower]
        spawned = []
        
        # Generate positions
        positions: list[tuple[int, int]] = []
        
        if x is not None and y is not None:
            # Single position specified
            positions.append((x, y))
            # Add nearby positions for additional enemies
            for i in range(1, count):
                offset_x = (i % 3) - 1
                offset_y = (i // 3)
                positions.append((x + offset_x, y + offset_y))
        elif room_x is not None and room_y is not None and room_width is not None and room_height is not None:
            # Spawn in room interior
            interior_x = room_x + 1
            interior_y = room_y + 1
            interior_w = max(1, room_width - 2)
            interior_h = max(1, room_height - 2)
            
            for i in range(count):
                px = interior_x + (i % interior_w)
                py = interior_y + (i // interior_w) % interior_h
                positions.append((px, py))
        else:
            return json.dumps({
                "success": False,
                "error": "Must specify either (x, y) position or room bounds (room_x, room_y, room_width, room_height).",
            })

        # Create NPCs
        existing_npc_count = len(state.npcs)
        
        for i, (px, py) in enumerate(positions[:count]):
            npc_id = f"npc-{enemy_type_lower}-{existing_npc_count + i + 1:03d}"
            
            # Generate a unique name
            if name_prefix:
                npc_name = f"{name_prefix} {template['base_name']}" if count == 1 else f"{name_prefix} {template['base_name']} {i + 1}"
            else:
                npc_name = template["base_name"] if count == 1 else f"{template['base_name']} {i + 1}"

            npc = NpcState(
                actor_id=npc_id,
                name=npc_name,
                role=template["role"],
                hp=template["hp"],
                max_hp=template["max_hp"],
                ac=template["ac"],
                initiative=template["initiative"],
                position=Position(x=px, y=py, zone_id="dungeon"),
                status_effects=[],
                inventory=list(template["inventory"]),
                spell_slots=dict(template.get("spell_slots", {})),
                disposition=template["disposition"],
                behavior_tag=template.get("behavior_tag"),
                visibility_scope=VisibilityScope(visibility=Visibility.PUBLIC),
            )
            
            state.npcs[npc_id] = npc
            spawned.append({
                "id": npc_id,
                "name": npc_name,
                "position": f"({px},{py})",
                "hp": npc.hp,
                "ac": npc.ac,
            })

        return json.dumps({
            "success": True,
            "spawned_count": len(spawned),
            "enemies": spawned,
            "message": f"Spawned {len(spawned)} {enemy_type}(s)",
        })

    return handle_spawn_enemies


def register_map_tools(registry: ToolRegistry, state: GameState | None) -> None:
    """Register DM map tools into the tool registry."""
    if state is None:
        return

    registry.register(AgentTool(
        name="place_tiles",
        description=(
            "Place or update tiles on the dungeon map. Use this to build the map, "
            "add walls, doors, terrain features, and objects. Changes are applied to "
            "the current game state. Pass a JSON array of change objects."
        ),
        parameters=[
            ToolParameter(
                name="changes",
                type="string",
                description=(
                    'JSON array of tile changes. Each object has: x (int), y (int), '
                    'and optionally: terrain ("floor","wall","door","door_locked",'
                    '"stairs_up","stairs_down","difficult","pit","water_deep"), '
                    'content ("empty","tree","altar","treasure_chest","campfire",'
                    '"pillar","statue","barrel","table","trap","torch","rubble",'
                    '"bookshelf","fountain","lever"), label (string), elevation (int).'
                ),
                required=True,
            ),
            ToolParameter(
                name="reveal",
                type="boolean",
                description="If true (default), mark changed tiles as revealed to players.",
                required=False,
            ),
        ],
        handler=_make_place_tiles_handler(state),
    ))

    registry.register(AgentTool(
        name="reveal_area",
        description=(
            "Reveal a rectangular area of the dungeon map (fog of war). "
            "Call this when players move into or can see a new area."
        ),
        parameters=[
            ToolParameter(name="x1", type="integer", description="Left column (inclusive)"),
            ToolParameter(name="y1", type="integer", description="Top row (inclusive)"),
            ToolParameter(name="x2", type="integer", description="Right column (inclusive)"),
            ToolParameter(name="y2", type="integer", description="Bottom row (inclusive)"),
        ],
        handler=_make_reveal_area_handler(state),
    ))

    registry.register(AgentTool(
        name="get_map_summary",
        description=(
            "Get a text/ASCII representation of the current dungeon map, "
            "showing terrain types, contents, and actor positions."
        ),
        parameters=[
            ToolParameter(
                name="show_all",
                type="boolean",
                description="If true, show the full map including unrevealed (fog of war) tiles.",
                required=False,
            ),
        ],
        handler=_make_get_map_summary_handler(state),
    ))

    # Procedural generation tools
    registry.register(AgentTool(
        name="init_map",
        description=(
            "Initialize a new empty dungeon map. Call this FIRST before generating rooms. "
            "Creates a map filled with walls that rooms can be carved into."
        ),
        parameters=[
            ToolParameter(
                name="name",
                type="string",
                description="Name for the dungeon map.",
                required=True,
            ),
            ToolParameter(
                name="width",
                type="integer",
                description="Map width in tiles (10-100).",
                required=True,
            ),
            ToolParameter(
                name="height",
                type="integer",
                description="Map height in tiles (10-100).",
                required=True,
            ),
            ToolParameter(
                name="default_terrain",
                type="string",
                description="Default terrain for all tiles (default: 'wall').",
                required=False,
            ),
        ],
        handler=_make_init_map_handler(state),
    ))

    registry.register(AgentTool(
        name="generate_room",
        description=(
            "Generate a room at a specific location. Creates walls around the perimeter "
            "and floor tiles inside. Use this to build the dungeon room by room."
        ),
        parameters=[
            ToolParameter(
                name="room_id",
                type="string",
                description="Unique identifier for this room (e.g., 'entrance', 'treasure_room').",
                required=True,
            ),
            ToolParameter(
                name="x",
                type="integer",
                description="Left edge x coordinate.",
                required=True,
            ),
            ToolParameter(
                name="y",
                type="integer",
                description="Top edge y coordinate.",
                required=True,
            ),
            ToolParameter(
                name="width",
                type="integer",
                description="Room width in tiles (including walls).",
                required=True,
            ),
            ToolParameter(
                name="height",
                type="integer",
                description="Room height in tiles (including walls).",
                required=True,
            ),
            ToolParameter(
                name="style",
                type="string",
                description="Room style: 'rectangular', 'irregular', 'circular', 'corridor', 'chamber'.",
                required=False,
            ),
            ToolParameter(
                name="revealed",
                type="boolean",
                description="Whether the room starts revealed to players (default: false).",
                required=False,
            ),
            ToolParameter(
                name="door_positions",
                type="string",
                description='JSON array of door specs: [{"side": "north"|"south"|"east"|"west", "offset": 2, "locked": false}].',
                required=False,
            ),
        ],
        handler=_make_generate_room_handler(state),
    ))

    registry.register(AgentTool(
        name="connect_rooms",
        description=(
            "Create a corridor connecting two points. Carves floor tiles through walls "
            "to connect rooms together."
        ),
        parameters=[
            ToolParameter(
                name="from_x",
                type="integer",
                description="Starting x coordinate.",
                required=True,
            ),
            ToolParameter(
                name="from_y",
                type="integer",
                description="Starting y coordinate.",
                required=True,
            ),
            ToolParameter(
                name="to_x",
                type="integer",
                description="Ending x coordinate.",
                required=True,
            ),
            ToolParameter(
                name="to_y",
                type="integer",
                description="Ending y coordinate.",
                required=True,
            ),
            ToolParameter(
                name="corridor_width",
                type="integer",
                description="Width of the corridor in tiles (default: 1).",
                required=False,
            ),
            ToolParameter(
                name="style",
                type="string",
                description="Corridor style: 'straight' (L-shaped) or 'winding' (random path).",
                required=False,
            ),
            ToolParameter(
                name="revealed",
                type="boolean",
                description="Whether the corridor starts revealed (default: false).",
                required=False,
            ),
        ],
        handler=_make_connect_rooms_handler(state),
    ))

    registry.register(AgentTool(
        name="populate_room",
        description=(
            "Fill a room with themed content like furniture, treasures, or traps. "
            "Call after generating the room structure."
        ),
        parameters=[
            ToolParameter(
                name="x",
                type="integer",
                description="Left edge of the room.",
                required=True,
            ),
            ToolParameter(
                name="y",
                type="integer",
                description="Top edge of the room.",
                required=True,
            ),
            ToolParameter(
                name="width",
                type="integer",
                description="Room width.",
                required=True,
            ),
            ToolParameter(
                name="height",
                type="integer",
                description="Room height.",
                required=True,
            ),
            ToolParameter(
                name="theme",
                type="string",
                description="Room theme: 'empty', 'storage', 'shrine', 'treasure', 'trap_room', 'living_quarters', 'library', 'fountain_room'.",
                required=False,
            ),
            ToolParameter(
                name="density",
                type="number",
                description="Content density (0.0-1.0, default: 0.3).",
                required=False,
            ),
            ToolParameter(
                name="seed",
                type="integer",
                description="Random seed for reproducible placement.",
                required=False,
            ),
        ],
        handler=_make_populate_room_handler(state),
    ))

    registry.register(AgentTool(
        name="spawn_enemies",
        description=(
            "Spawn enemy NPCs on the map. Use this to place enemies in rooms or at specific positions. "
            "Enemies are added to the game state and will appear on the map."
        ),
        parameters=[
            ToolParameter(
                name="enemy_type",
                type="string",
                description="Type of enemy to spawn: 'goblin', 'goblin_shaman', 'skeleton', 'zombie', 'bandit', 'cultist', 'giant_spider', 'wolf'.",
                required=True,
            ),
            ToolParameter(
                name="count",
                type="integer",
                description="Number of enemies to spawn (default: 1).",
                required=False,
            ),
            ToolParameter(
                name="x",
                type="integer",
                description="X coordinate to spawn at (use with y for specific position).",
                required=False,
            ),
            ToolParameter(
                name="y",
                type="integer",
                description="Y coordinate to spawn at (use with x for specific position).",
                required=False,
            ),
            ToolParameter(
                name="room_x",
                type="integer",
                description="Room left edge (use with room_y, room_width, room_height to spawn in a room).",
                required=False,
            ),
            ToolParameter(
                name="room_y",
                type="integer",
                description="Room top edge.",
                required=False,
            ),
            ToolParameter(
                name="room_width",
                type="integer",
                description="Room width.",
                required=False,
            ),
            ToolParameter(
                name="room_height",
                type="integer",
                description="Room height.",
                required=False,
            ),
            ToolParameter(
                name="name_prefix",
                type="string",
                description="Optional name prefix for the enemy (e.g., 'Guard' for 'Guard Goblin').",
                required=False,
            ),
        ],
        handler=_make_spawn_enemies_handler(state),
    ))
