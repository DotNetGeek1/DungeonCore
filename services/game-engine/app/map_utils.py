from __future__ import annotations

from shared_schemas.state import DungeonMap, MapTile, Position, TerrainType

IMPASSABLE_TERRAIN = {TerrainType.WALL, TerrainType.PIT, TerrainType.WATER_DEEP}
DIFFICULT_TERRAIN = {TerrainType.DIFFICULT}
DOOR_TERRAIN = {TerrainType.DOOR, TerrainType.DOOR_LOCKED}

MOVEMENT_COST_NORMAL = 1
MOVEMENT_COST_DIFFICULT = 2


def is_walkable(tile: MapTile) -> bool:
    """Returns True if an actor can enter this tile.
    
    Walls, pits, and deep water are always impassable.
    Doors must be open to pass through.
    """
    if tile.terrain in IMPASSABLE_TERRAIN:
        return False
    # Doors must be open to walk through
    if tile.terrain in DOOR_TERRAIN:
        return tile.door_open
    return True


def is_door(tile: MapTile) -> bool:
    """Returns True if the tile is any kind of door."""
    return tile.terrain in DOOR_TERRAIN


def is_closed_door(tile: MapTile) -> bool:
    """Returns True if the tile is a closed door (locked or unlocked)."""
    return tile.terrain in DOOR_TERRAIN and not tile.door_open


def is_locked_door(tile: MapTile) -> bool:
    """Returns True if the tile is a locked door."""
    return tile.terrain == TerrainType.DOOR_LOCKED


def can_open_door(tile: MapTile) -> bool:
    """Returns True if the door can be opened (unlocked and closed)."""
    return tile.terrain == TerrainType.DOOR and not tile.door_open


def tile_movement_cost(tile: MapTile) -> int:
    """Returns the movement cost in squares to enter this tile."""
    if tile.terrain in DIFFICULT_TERRAIN:
        return MOVEMENT_COST_DIFFICULT
    return MOVEMENT_COST_NORMAL


def chebyshev_distance(x1: int, y1: int, x2: int, y2: int) -> int:
    """Chebyshev (chessboard) distance — D&D 5e uses this for diagonal movement."""
    return max(abs(x2 - x1), abs(y2 - y1))


def is_adjacent(x1: int, y1: int, x2: int, y2: int) -> bool:
    """Returns True if the two positions are adjacent (including diagonals)."""
    return chebyshev_distance(x1, y1, x2, y2) == 1


def get_tile(dungeon_map: DungeonMap, x: int, y: int) -> MapTile | None:
    """Safely get a tile from the map, returning None if out of bounds."""
    if 0 <= y < dungeon_map.height and 0 <= x < dungeon_map.width:
        return dungeon_map.tiles[y][x]
    return None


def parse_coord(coord_str: str) -> tuple[int, int] | None:
    """Parse a coordinate string 'x,y' into a tuple. Returns None on failure."""
    try:
        parts = coord_str.split(",")
        if len(parts) == 2:
            return int(parts[0].strip()), int(parts[1].strip())
    except (ValueError, AttributeError):
        pass
    return None


def path_movement_cost(dungeon_map: DungeonMap, path: list[str]) -> int:
    """
    Calculate total movement cost for a list of coordinate strings ('x,y').
    Skips the first element (starting position). Impassable tiles add their
    base cost but callers should separately check walkability.
    """
    total = 0
    for coord_str in path[1:]:
        coords = parse_coord(coord_str)
        if coords is None:
            total += MOVEMENT_COST_NORMAL
            continue
        x, y = coords
        tile = get_tile(dungeon_map, x, y)
        if tile is not None:
            total += tile_movement_cost(tile)
        else:
            total += MOVEMENT_COST_NORMAL
    return total


def validate_path_on_map(
    dungeon_map: DungeonMap,
    start: Position,
    path: list[str],
    movement_budget: int,
) -> list[str]:
    """
    Validate a movement path against the dungeon map.

    Args:
        dungeon_map: The current dungeon map.
        start: Actor's current position.
        path: List of 'x,y' coordinate strings (may include start or not).
        movement_budget: Maximum movement squares available.

    Returns:
        List of error strings (empty = valid).
    """
    errors: list[str] = []

    if not path:
        errors.append("Movement path is empty")
        return errors

    # Normalise: strip the starting position from path if present
    first = parse_coord(path[0])
    if first is not None and first == (start.x, start.y):
        path = path[1:]

    if not path:
        errors.append("Movement path contains only the starting position")
        return errors

    prev_x, prev_y = start.x, start.y
    total_cost = 0

    for i, coord_str in enumerate(path):
        coords = parse_coord(coord_str)
        if coords is None:
            errors.append(
                f"Path step {i + 1} '{coord_str}' is not a valid 'x,y' coordinate"
            )
            return errors

        x, y = coords

        tile = get_tile(dungeon_map, x, y)
        if tile is None:
            errors.append(
                f"Path step {i + 1} ({x},{y}) is outside the map bounds "
                f"({dungeon_map.width}x{dungeon_map.height})"
            )
            return errors

        if not is_walkable(tile):
            # Give specific error messages for doors
            if tile.terrain == TerrainType.DOOR_LOCKED and not tile.door_open:
                errors.append(
                    f"Path step {i + 1} ({x},{y}) is a locked door - must be unlocked first"
                )
            elif tile.terrain == TerrainType.DOOR and not tile.door_open:
                errors.append(
                    f"Path step {i + 1} ({x},{y}) is a closed door - use 'interact' action to open it first"
                )
            else:
                errors.append(
                    f"Path step {i + 1} ({x},{y}) is impassable terrain: {tile.terrain}"
                )
            return errors

        if not is_adjacent(prev_x, prev_y, x, y):
            errors.append(
                f"Path step {i + 1} ({x},{y}) is not adjacent to previous "
                f"position ({prev_x},{prev_y})"
            )
            return errors

        total_cost += tile_movement_cost(tile)
        prev_x, prev_y = x, y

    if total_cost > movement_budget:
        errors.append(
            f"Movement path costs {total_cost} squares but budget is {movement_budget}"
        )

    return errors
