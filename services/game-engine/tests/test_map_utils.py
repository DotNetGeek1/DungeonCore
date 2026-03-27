"""Tests for game engine map utilities and map-aware validators."""

from __future__ import annotations

import pytest

from shared_schemas.enums import ActorRole, ScenePhase, Visibility
from shared_schemas.actions import AttackAction, MoveAction, MoveAndAttackAction
from shared_schemas.enums import ActionType
from shared_schemas.state import (
    CharacterState,
    DungeonMap,
    GameState,
    MapTile,
    NpcState,
    ObjectiveState,
    Position,
    SceneState,
    TerrainType,
    TileContent,
    TurnState,
    VisibilityScope,
)

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.map_utils import (
    chebyshev_distance,
    get_tile,
    is_adjacent,
    is_walkable,
    parse_coord,
    path_movement_cost,
    tile_movement_cost,
    validate_path_on_map,
)
from app.validators.attack import AttackValidator
from app.validators.move import MoveValidator
from app.validators.move_and_attack import MoveAndAttackValidator


def make_tile(terrain: TerrainType = TerrainType.FLOOR, content: TileContent = TileContent.EMPTY, revealed: bool = True) -> MapTile:
    return MapTile(terrain=terrain, content=content, revealed=revealed)


def make_simple_map(width: int = 5, height: int = 5) -> DungeonMap:
    """
    Create a simple 5x5 map:
    . . # . .
    . . # . .
    . . D . .
    . . . . .
    . . . . .
    """
    tiles = []
    for y in range(height):
        row = []
        for x in range(width):
            if x == 2 and y < 2:
                row.append(make_tile(TerrainType.WALL))
            elif x == 2 and y == 2:
                row.append(make_tile(TerrainType.DOOR))
            else:
                row.append(make_tile(TerrainType.FLOOR))
        tiles.append(row)
    # Add difficult terrain at (1,3)
    tiles[3][1] = make_tile(TerrainType.DIFFICULT)
    return DungeonMap(name="Test Map", width=width, height=height, tiles=tiles)


def make_game_state_with_map(dungeon_map: DungeonMap | None = None) -> GameState:
    return GameState(
        campaign_id="c1",
        session_id="s1",
        scene=SceneState(
            scene_id="scene-1",
            name="Test",
            summary="Test scene",
            turn_number=1,
            active_actor_id="player-1",
            phase=ScenePhase.ACTION_COMMIT,
        ),
        turn=TurnState(
            turn_number=1,
            round_number=1,
            active_actor_id="player-1",
            phase=ScenePhase.ACTION_COMMIT,
        ),
        characters={
            "player-1": CharacterState(
                actor_id="player-1",
                name="Fighter",
                role=ActorRole.PLAYER,
                hp=20,
                max_hp=20,
                ac=16,
                position=Position(x=0, y=0),
                visibility_scope=VisibilityScope(visibility=Visibility.PUBLIC),
            ),
        },
        npcs={
            "goblin-1": NpcState(
                actor_id="goblin-1",
                name="Goblin",
                role=ActorRole.NPC,
                hp=7,
                max_hp=7,
                ac=12,
                disposition="hostile",
                position=Position(x=1, y=0),
                visibility_scope=VisibilityScope(visibility=Visibility.PUBLIC),
            ),
        },
        objectives=[],
        flags={},
        dungeon_map=dungeon_map,
    )


class TestChebyshevDistance:
    def test_same_position(self) -> None:
        assert chebyshev_distance(3, 3, 3, 3) == 0

    def test_orthogonal_adjacent(self) -> None:
        assert chebyshev_distance(0, 0, 1, 0) == 1
        assert chebyshev_distance(0, 0, 0, 1) == 1

    def test_diagonal_adjacent(self) -> None:
        assert chebyshev_distance(0, 0, 1, 1) == 1

    def test_farther_diagonal(self) -> None:
        assert chebyshev_distance(0, 0, 3, 2) == 3

    def test_negative_direction(self) -> None:
        assert chebyshev_distance(5, 5, 2, 3) == 3


class TestIsAdjacent:
    def test_adjacent_right(self) -> None:
        assert is_adjacent(0, 0, 1, 0) is True

    def test_adjacent_diagonal(self) -> None:
        assert is_adjacent(0, 0, 1, 1) is True

    def test_not_adjacent(self) -> None:
        assert is_adjacent(0, 0, 2, 0) is False

    def test_same_position(self) -> None:
        assert is_adjacent(0, 0, 0, 0) is False


class TestParseCoord:
    def test_valid_coord(self) -> None:
        assert parse_coord("3,5") == (3, 5)

    def test_with_spaces(self) -> None:
        assert parse_coord("3, 5") == (3, 5)

    def test_invalid_format(self) -> None:
        assert parse_coord("A1") is None

    def test_missing_comma(self) -> None:
        assert parse_coord("35") is None


class TestIsWalkable:
    def test_floor_is_walkable(self) -> None:
        tile = make_tile(TerrainType.FLOOR)
        assert is_walkable(tile) is True

    def test_wall_is_not_walkable(self) -> None:
        tile = make_tile(TerrainType.WALL)
        assert is_walkable(tile) is False

    def test_pit_is_not_walkable(self) -> None:
        tile = make_tile(TerrainType.PIT)
        assert is_walkable(tile) is False

    def test_closed_door_is_not_walkable(self) -> None:
        tile = make_tile(TerrainType.DOOR)
        assert tile.door_open is False  # Doors start closed
        assert is_walkable(tile) is False

    def test_open_door_is_walkable(self) -> None:
        tile = MapTile(terrain=TerrainType.DOOR, door_open=True)
        assert is_walkable(tile) is True

    def test_difficult_is_walkable(self) -> None:
        tile = make_tile(TerrainType.DIFFICULT)
        assert is_walkable(tile) is True


class TestTileMovementCost:
    def test_floor_costs_one(self) -> None:
        tile = make_tile(TerrainType.FLOOR)
        assert tile_movement_cost(tile) == 1

    def test_difficult_costs_two(self) -> None:
        tile = make_tile(TerrainType.DIFFICULT)
        assert tile_movement_cost(tile) == 2

    def test_door_costs_one(self) -> None:
        tile = make_tile(TerrainType.DOOR)
        assert tile_movement_cost(tile) == 1


class TestGetTile:
    def test_get_in_bounds(self) -> None:
        dm = make_simple_map()
        tile = get_tile(dm, 0, 0)
        assert tile is not None
        assert tile.terrain == TerrainType.FLOOR

    def test_get_out_of_bounds(self) -> None:
        dm = make_simple_map()
        assert get_tile(dm, 10, 10) is None
        assert get_tile(dm, -1, 0) is None


class TestValidatePathOnMap:
    def test_valid_simple_path(self) -> None:
        dm = make_simple_map()
        start = Position(x=0, y=0)
        path = ["1,0", "1,1"]
        errors = validate_path_on_map(dm, start, path, 6)
        assert errors == []

    def test_path_through_wall_fails(self) -> None:
        dm = make_simple_map()
        start = Position(x=1, y=0)
        path = ["2,0"]
        errors = validate_path_on_map(dm, start, path, 6)
        assert len(errors) > 0
        assert any("impassable" in e for e in errors)

    def test_path_non_adjacent_fails(self) -> None:
        dm = make_simple_map()
        start = Position(x=0, y=0)
        path = ["3,0"]  # Skip 2 squares
        errors = validate_path_on_map(dm, start, path, 6)
        assert len(errors) > 0
        assert any("adjacent" in e for e in errors)

    def test_path_exceeds_budget_fails(self) -> None:
        dm = make_simple_map()
        start = Position(x=0, y=0)
        path = ["1,0", "1,1", "1,2", "1,3", "1,4"]
        errors = validate_path_on_map(dm, start, path, 3)
        assert len(errors) > 0
        assert any("budget" in e or "cost" in e for e in errors)

    def test_difficult_terrain_counts_double(self) -> None:
        dm = make_simple_map()
        start = Position(x=0, y=3)
        # (1,3) is difficult, costs 2
        path = ["1,3"]
        errors = validate_path_on_map(dm, start, path, 1)
        assert len(errors) > 0  # costs 2, budget is 1

        errors_ok = validate_path_on_map(dm, start, path, 2)
        assert errors_ok == []

    def test_path_through_closed_door_fails(self) -> None:
        dm = make_simple_map()
        start = Position(x=1, y=2)
        path = ["2,2"]  # Closed door tile
        errors = validate_path_on_map(dm, start, path, 6)
        assert len(errors) > 0
        assert "closed door" in errors[0].lower()

    def test_path_through_open_door_is_valid(self) -> None:
        dm = make_simple_map()
        # Open the door at (2, 2)
        dm.tiles[2][2] = MapTile(terrain=TerrainType.DOOR, door_open=True)
        start = Position(x=1, y=2)
        path = ["2,2"]  # Now open door tile
        errors = validate_path_on_map(dm, start, path, 6)
        assert errors == []

    def test_path_starting_at_start_position_is_stripped(self) -> None:
        dm = make_simple_map()
        start = Position(x=0, y=0)
        path = ["0,0", "1,0"]  # First elem = start
        errors = validate_path_on_map(dm, start, path, 6)
        assert errors == []


class TestMapAwareAttackValidator:
    def test_adjacent_attack_succeeds(self) -> None:
        dm = make_simple_map()
        state = make_game_state_with_map(dm)
        validator = AttackValidator()
        action = AttackAction(type=ActionType.ATTACK, target_id="goblin-1")
        result = validator.validate(action, "player-1", state)
        assert result.valid is True

    def test_out_of_range_attack_fails(self) -> None:
        dm = make_simple_map()
        state = make_game_state_with_map(dm)
        # Move goblin far away
        far_goblin = state.npcs["goblin-1"].model_copy(
            update={"position": Position(x=4, y=4)}
        )
        state = state.model_copy(update={"npcs": {"goblin-1": far_goblin}})
        validator = AttackValidator()
        action = AttackAction(type=ActionType.ATTACK, target_id="goblin-1")
        result = validator.validate(action, "player-1", state)
        assert result.valid is False
        assert any("reach" in e.lower() or "range" in e.lower() for e in result.errors)

    def test_no_map_attack_ignores_range(self) -> None:
        """Without a map, range is not checked."""
        state = make_game_state_with_map(None)
        validator = AttackValidator()
        action = AttackAction(type=ActionType.ATTACK, target_id="goblin-1")
        result = validator.validate(action, "player-1", state)
        assert result.valid is True


class TestMapAwareMoveValidator:
    def test_valid_path_on_map(self) -> None:
        dm = make_simple_map()
        state = make_game_state_with_map(dm)
        validator = MoveValidator()
        action = MoveAction(type=ActionType.MOVE, movement_path=["1,0", "1,1"])
        result = validator.validate(action, "player-1", state)
        assert result.valid is True

    def test_path_through_wall_fails(self) -> None:
        dm = make_simple_map()
        state = make_game_state_with_map(dm)
        # player is at (0,0), try going right through wall at (2,0)
        state = state.model_copy(update={
            "characters": {
                "player-1": state.characters["player-1"].model_copy(
                    update={"position": Position(x=1, y=0)}
                )
            }
        })
        validator = MoveValidator()
        action = MoveAction(type=ActionType.MOVE, movement_path=["2,0"])
        result = validator.validate(action, "player-1", state)
        assert result.valid is False

    def test_no_map_uses_length_fallback(self) -> None:
        state = make_game_state_with_map(None)
        validator = MoveValidator()
        action = MoveAction(type=ActionType.MOVE, movement_path=["A1", "A2", "A3"])
        result = validator.validate(action, "player-1", state)
        assert result.valid is True
