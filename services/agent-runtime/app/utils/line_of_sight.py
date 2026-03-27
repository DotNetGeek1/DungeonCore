"""Line of Sight (LOS) calculation utilities for dungeon visibility.

This module provides functions to determine what positions are visible from
a given point, accounting for walls and other blocking terrain. Uses 
Bresenham's line algorithm for efficient integer-based ray tracing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from shared_schemas.state import DungeonMap, TerrainType


# Terrain types that block line of sight
BLOCKING_TERRAIN: set[str] = {"wall"}

# Default vision range in grid squares (60 feet = 12 squares at 5ft/square)
DEFAULT_VISION_RANGE = 12


def _get_line_points(x0: int, y0: int, x1: int, y1: int) -> list[tuple[int, int]]:
    """Generate all points along a line using Bresenham's algorithm.
    
    Returns points from (x0, y0) to (x1, y1) inclusive.
    """
    points = []
    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    x, y = x0, y0
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    
    if dx > dy:
        err = dx / 2
        while x != x1:
            points.append((x, y))
            err -= dy
            if err < 0:
                y += sy
                err += dx
            x += sx
        points.append((x, y))
    else:
        err = dy / 2
        while y != y1:
            points.append((x, y))
            err -= dx
            if err < 0:
                x += sx
                err += dy
            y += sy
        points.append((x, y))
    
    return points


def has_line_of_sight(
    dungeon_map: DungeonMap,
    from_x: int,
    from_y: int,
    to_x: int,
    to_y: int,
    blocking_terrain: set[str] | None = None,
) -> bool:
    """Check if there is unobstructed line of sight between two points.
    
    Args:
        dungeon_map: The dungeon map to check against.
        from_x: Starting X coordinate.
        from_y: Starting Y coordinate.
        to_x: Target X coordinate.
        to_y: Target Y coordinate.
        blocking_terrain: Set of terrain type strings that block LOS.
                         Defaults to {"wall"}.
    
    Returns:
        True if there is clear line of sight, False if blocked.
    """
    if blocking_terrain is None:
        blocking_terrain = BLOCKING_TERRAIN
    
    # Same position always has LOS
    if from_x == to_x and from_y == to_y:
        return True
    
    # Get all points along the line
    line_points = _get_line_points(from_x, from_y, to_x, to_y)
    
    # Check each point (except start and end) for blocking terrain
    # We skip the first point (observer) and last point (target)
    # because you can see from/to a position even if it's a wall
    for x, y in line_points[1:-1]:
        # Out of bounds is blocking
        if not (0 <= x < dungeon_map.width and 0 <= y < dungeon_map.height):
            return False
        
        tile = dungeon_map.tiles[y][x]
        if tile.terrain in blocking_terrain:
            return False
    
    return True


def get_visible_positions_from_point(
    dungeon_map: DungeonMap,
    origin_x: int,
    origin_y: int,
    vision_range: int = DEFAULT_VISION_RANGE,
    blocking_terrain: set[str] | None = None,
) -> set[tuple[int, int]]:
    """Get all positions visible from a single point.
    
    Uses raycasting to determine visibility within the vision range.
    
    Args:
        dungeon_map: The dungeon map to check against.
        origin_x: Observer's X coordinate.
        origin_y: Observer's Y coordinate.
        vision_range: Maximum vision distance in squares.
        blocking_terrain: Set of terrain types that block LOS.
    
    Returns:
        Set of (x, y) tuples that are visible from the origin.
    """
    if blocking_terrain is None:
        blocking_terrain = BLOCKING_TERRAIN
    
    visible: set[tuple[int, int]] = set()
    
    # Always can see your own position
    visible.add((origin_x, origin_y))
    
    # Calculate bounding box for vision range
    min_x = max(0, origin_x - vision_range)
    max_x = min(dungeon_map.width - 1, origin_x + vision_range)
    min_y = max(0, origin_y - vision_range)
    max_y = min(dungeon_map.height - 1, origin_y + vision_range)
    
    # Cast rays to perimeter of vision range and mark all visible tiles
    # We check the perimeter of the bounding box plus intermediate points
    
    # Check all tiles within range
    for target_y in range(min_y, max_y + 1):
        for target_x in range(min_x, max_x + 1):
            # Skip if outside circular vision range
            dx = target_x - origin_x
            dy = target_y - origin_y
            if dx * dx + dy * dy > vision_range * vision_range:
                continue
            
            # Check line of sight
            if has_line_of_sight(
                dungeon_map,
                origin_x, origin_y,
                target_x, target_y,
                blocking_terrain,
            ):
                visible.add((target_x, target_y))
    
    return visible


def get_visible_positions_for_players(
    dungeon_map: DungeonMap | None,
    player_positions: list[tuple[int, int]],
    vision_range: int = DEFAULT_VISION_RANGE,
    blocking_terrain: set[str] | None = None,
) -> set[tuple[int, int]]:
    """Get all positions visible to any player character.
    
    This is the union of what all players can see, supporting the
    "shared party vision" model where if any player sees something,
    the whole party knows about it.
    
    Args:
        dungeon_map: The dungeon map, or None if no map exists.
        player_positions: List of (x, y) positions for all players.
        vision_range: Maximum vision distance in squares.
        blocking_terrain: Set of terrain types that block LOS.
    
    Returns:
        Set of (x, y) tuples visible to at least one player.
        Returns empty set if no map or no players.
    """
    if dungeon_map is None or not player_positions:
        return set()
    
    if blocking_terrain is None:
        blocking_terrain = BLOCKING_TERRAIN
    
    all_visible: set[tuple[int, int]] = set()
    
    for px, py in player_positions:
        player_visible = get_visible_positions_from_point(
            dungeon_map,
            px, py,
            vision_range,
            blocking_terrain,
        )
        all_visible.update(player_visible)
    
    return all_visible


def is_position_visible_to_players(
    dungeon_map: DungeonMap | None,
    target_x: int,
    target_y: int,
    player_positions: list[tuple[int, int]],
    vision_range: int = DEFAULT_VISION_RANGE,
    blocking_terrain: set[str] | None = None,
) -> bool:
    """Check if a specific position is visible to any player.
    
    This is more efficient than get_visible_positions_for_players when
    you only need to check a single position.
    
    Args:
        dungeon_map: The dungeon map, or None if no map exists.
        target_x: X coordinate to check visibility for.
        target_y: Y coordinate to check visibility for.
        player_positions: List of (x, y) positions for all players.
        vision_range: Maximum vision distance in squares.
        blocking_terrain: Set of terrain types that block LOS.
    
    Returns:
        True if any player can see the target position.
    """
    if dungeon_map is None or not player_positions:
        return False
    
    if blocking_terrain is None:
        blocking_terrain = BLOCKING_TERRAIN
    
    for px, py in player_positions:
        # Check range first (cheaper than LOS calculation)
        dx = target_x - px
        dy = target_y - py
        if dx * dx + dy * dy > vision_range * vision_range:
            continue
        
        # Check line of sight
        if has_line_of_sight(
            dungeon_map,
            px, py,
            target_x, target_y,
            blocking_terrain,
        ):
            return True
    
    return False
