"""Direct unit tests for game engine CombatResolver."""

from __future__ import annotations

import pytest

from shared_schemas.actions import (
    AttackAction,
    CastSpellBasicAction,
    DefendAction,
    InspectAction,
    MoveAction,
    MoveAndAttackAction,
)
from shared_schemas.enums import ActionType, ActorRole, ScenePhase, Visibility
from shared_schemas.state import (
    CharacterState,
    GameState,
    NpcState,
    Position,
    SceneState,
    TurnState,
    VisibilityScope,
)

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.dice import DiceRoller
from app.resolution.combat import CombatResolver, ResolutionResult, StatePatch


@pytest.fixture
def base_state() -> GameState:
    """Create a base game state for testing."""
    return GameState(
        campaign_id="campaign-test",
        session_id="session-test",
        scene=SceneState(
            scene_id="scene-test",
            name="Test Scene",
            summary="A test scene",
            turn_number=1,
            active_actor_id="player-1",
            phase=ScenePhase.RESOLUTION,
        ),
        turn=TurnState(
            turn_number=1,
            round_number=1,
            active_actor_id="player-1",
            phase=ScenePhase.RESOLUTION,
        ),
        characters={
            "player-1": CharacterState(
                actor_id="player-1",
                name="Fighter",
                role=ActorRole.PLAYER,
                hp=20,
                max_hp=20,
                ac=16,
                position=Position(x=1, y=1, node_id="A1", zone_id="dungeon"),
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
                position=Position(x=5, y=1, node_id="A5", zone_id="dungeon"),
                visibility_scope=VisibilityScope(visibility=Visibility.PUBLIC),
            ),
        },
        objectives=[],
        flags={},
    )


@pytest.fixture
def seeded_resolver() -> CombatResolver:
    """Create a resolver with a seeded dice roller for deterministic tests."""
    return CombatResolver(DiceRoller(seed=42))


class TestAttackResolution:
    def test_attack_hit_applies_damage(self, base_state: GameState) -> None:
        resolver = CombatResolver(DiceRoller(seed=100))
        action = AttackAction(type=ActionType.ATTACK, target_id="goblin-1")

        result = resolver.resolve(action, "player-1", base_state)

        assert result.success is True
        assert result.action_type == ActionType.ATTACK
        assert result.hit is not None
        assert len(result.dice_rolls) >= 1
        if result.hit:
            assert result.damage is not None
            assert result.damage > 0
            assert any(p.target_id == "goblin-1" and p.field == "hp" for p in result.state_patches)

    def test_attack_deterministic_with_seed(self, base_state: GameState) -> None:
        resolver1 = CombatResolver(DiceRoller(seed=42))
        resolver2 = CombatResolver(DiceRoller(seed=42))
        action = AttackAction(type=ActionType.ATTACK, target_id="goblin-1")

        result1 = resolver1.resolve(action, "player-1", base_state)
        result2 = resolver2.resolve(action, "player-1", base_state)

        assert result1.hit == result2.hit
        assert result1.damage == result2.damage
        assert len(result1.dice_rolls) == len(result2.dice_rolls)
        for r1, r2 in zip(result1.dice_rolls, result2.dice_rolls):
            assert r1.value == r2.value

    def test_attack_records_dice_rolls(self, seeded_resolver: CombatResolver, base_state: GameState) -> None:
        action = AttackAction(type=ActionType.ATTACK, target_id="goblin-1")

        result = seeded_resolver.resolve(action, "player-1", base_state)

        assert len(result.dice_rolls) >= 1
        attack_roll = result.dice_rolls[0]
        assert attack_roll.die == "d20"
        assert 1 <= attack_roll.value <= 20

    def test_attack_description_includes_roll_info(self, seeded_resolver: CombatResolver, base_state: GameState) -> None:
        action = AttackAction(type=ActionType.ATTACK, target_id="goblin-1")

        result = seeded_resolver.resolve(action, "player-1", base_state)

        assert "vs AC" in result.description
        assert "rolled" in result.description


class TestMoveResolution:
    def test_move_creates_position_patch(self, seeded_resolver: CombatResolver, base_state: GameState) -> None:
        action = MoveAction(type=ActionType.MOVE, movement_path=["A1", "A2", "A3"])

        result = seeded_resolver.resolve(action, "player-1", base_state)

        assert result.success is True
        assert result.action_type == ActionType.MOVE
        assert len(result.state_patches) == 1
        
        patch = result.state_patches[0]
        assert patch.patch_type == "move"
        assert patch.target_id == "player-1"
        assert patch.field == "position"
        # new_value is a Position dict with node_id set to last path element
        assert isinstance(patch.new_value, dict)
        assert patch.new_value.get("node_id") == "A3"

    def test_move_has_no_dice_rolls(self, seeded_resolver: CombatResolver, base_state: GameState) -> None:
        action = MoveAction(type=ActionType.MOVE, movement_path=["A1", "A2"])

        result = seeded_resolver.resolve(action, "player-1", base_state)

        assert len(result.dice_rolls) == 0

    def test_move_description_shows_path(self, seeded_resolver: CombatResolver, base_state: GameState) -> None:
        action = MoveAction(type=ActionType.MOVE, movement_path=["A1", "A2", "B2"])

        result = seeded_resolver.resolve(action, "player-1", base_state)

        assert "B2" in result.description


class TestDefendResolution:
    def test_defend_guard_stance(self, seeded_resolver: CombatResolver, base_state: GameState) -> None:
        action = DefendAction(type=ActionType.DEFEND, stance="guard")

        result = seeded_resolver.resolve(action, "player-1", base_state)

        assert result.success is True
        assert result.action_type == ActionType.DEFEND
        assert "guard" in result.description
        assert "+2 AC" in result.description

    def test_defend_dodge_stance(self, seeded_resolver: CombatResolver, base_state: GameState) -> None:
        action = DefendAction(type=ActionType.DEFEND, stance="dodge")

        result = seeded_resolver.resolve(action, "player-1", base_state)

        assert result.success is True
        assert "dodge" in result.description
        assert "Dex" in result.description

    def test_defend_brace_stance(self, seeded_resolver: CombatResolver, base_state: GameState) -> None:
        action = DefendAction(type=ActionType.DEFEND, stance="brace")

        result = seeded_resolver.resolve(action, "player-1", base_state)

        assert result.success is True
        assert "brace" in result.description
        assert "Halve" in result.description

    def test_defend_has_no_state_patches(self, seeded_resolver: CombatResolver, base_state: GameState) -> None:
        action = DefendAction(type=ActionType.DEFEND, stance="guard")

        result = seeded_resolver.resolve(action, "player-1", base_state)

        assert len(result.state_patches) == 0


class TestInspectResolution:
    def test_inspect_target(self, seeded_resolver: CombatResolver, base_state: GameState) -> None:
        action = InspectAction(type=ActionType.INSPECT, target_id="goblin-1")

        result = seeded_resolver.resolve(action, "player-1", base_state)

        assert result.success is True
        assert result.action_type == ActionType.INSPECT
        assert "goblin-1" in result.description

    def test_inspect_location(self, seeded_resolver: CombatResolver, base_state: GameState) -> None:
        action = InspectAction(type=ActionType.INSPECT, location_id="room-corner")

        result = seeded_resolver.resolve(action, "player-1", base_state)

        assert result.success is True
        assert "room-corner" in result.description


class TestMoveAndAttackResolution:
    def test_move_and_attack_combines_results(self, seeded_resolver: CombatResolver, base_state: GameState) -> None:
        action = MoveAndAttackAction(
            type=ActionType.MOVE_AND_ATTACK,
            movement_path=["A1", "A2", "A3"],
            target_id="goblin-1",
        )

        result = seeded_resolver.resolve(action, "player-1", base_state)

        assert result.success is True
        assert result.action_type == ActionType.MOVE_AND_ATTACK
        assert result.hit is not None
        assert any(p.patch_type == "move" for p in result.state_patches)

    def test_move_and_attack_has_attack_dice(self, seeded_resolver: CombatResolver, base_state: GameState) -> None:
        action = MoveAndAttackAction(
            type=ActionType.MOVE_AND_ATTACK,
            movement_path=["A1", "A2"],
            target_id="goblin-1",
        )

        result = seeded_resolver.resolve(action, "player-1", base_state)

        assert len(result.dice_rolls) >= 1

    def test_move_and_attack_description_includes_both(self, seeded_resolver: CombatResolver, base_state: GameState) -> None:
        action = MoveAndAttackAction(
            type=ActionType.MOVE_AND_ATTACK,
            movement_path=["A1", "A2"],
            target_id="goblin-1",
        )

        result = seeded_resolver.resolve(action, "player-1", base_state)

        assert "Moved" in result.description or "Move" in result.description
        assert "vs AC" in result.description or "Attack" in result.description


class TestCastSpellResolution:
    def test_cast_spell_on_target(self, seeded_resolver: CombatResolver, base_state: GameState) -> None:
        action = CastSpellBasicAction(
            type=ActionType.CAST_SPELL_BASIC,
            spell_id="fire-bolt",
            target_id="goblin-1",
        )

        result = seeded_resolver.resolve(action, "player-1", base_state)

        assert result.success is True
        assert result.action_type == ActionType.CAST_SPELL_BASIC
        assert result.hit is not None
        assert len(result.dice_rolls) >= 1

    def test_cast_spell_without_target(self, seeded_resolver: CombatResolver, base_state: GameState) -> None:
        action = CastSpellBasicAction(
            type=ActionType.CAST_SPELL_BASIC,
            spell_id="shield",
        )

        result = seeded_resolver.resolve(action, "player-1", base_state)

        assert result.success is True
        assert result.hit is None
        assert "shield" in result.description

    def test_cast_spell_hit_applies_damage(self, base_state: GameState) -> None:
        resolver = CombatResolver(DiceRoller(seed=100))
        action = CastSpellBasicAction(
            type=ActionType.CAST_SPELL_BASIC,
            spell_id="fire-bolt",
            target_id="goblin-1",
        )

        result = resolver.resolve(action, "player-1", base_state)

        if result.hit:
            assert result.damage is not None
            assert any(p.field == "hp" for p in result.state_patches)


class TestStatePatch:
    def test_state_patch_dataclass(self) -> None:
        patch = StatePatch(
            patch_type="damage",
            target_id="goblin-1",
            field="hp",
            old_value=7,
            new_value=3,
        )

        assert patch.patch_type == "damage"
        assert patch.target_id == "goblin-1"
        assert patch.field == "hp"
        assert patch.old_value == 7
        assert patch.new_value == 3


class TestResolutionResult:
    def test_resolution_result_defaults(self) -> None:
        result = ResolutionResult(success=True, action_type=ActionType.DEFEND)

        assert result.dice_rolls == []
        assert result.state_patches == []
        assert result.description == ""
        assert result.hit is None
        assert result.damage is None

    def test_resolution_result_with_all_fields(self) -> None:
        result = ResolutionResult(
            success=True,
            action_type=ActionType.ATTACK,
            dice_rolls=[],
            state_patches=[],
            description="Hit for 5 damage",
            hit=True,
            damage=5,
        )

        assert result.success is True
        assert result.hit is True
        assert result.damage == 5
