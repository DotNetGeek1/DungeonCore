"""Direct unit tests for game engine validators."""

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
    SceneState,
    TurnState,
    VisibilityScope,
)

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.validators import (
    AttackValidator,
    CastSpellValidator,
    DefendValidator,
    InspectValidator,
    MoveValidator,
    MoveAndAttackValidator,
)


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
                visibility_scope=VisibilityScope(visibility=Visibility.PUBLIC),
            ),
            "player-2": CharacterState(
                actor_id="player-2",
                name="Rogue",
                role=ActorRole.PLAYER,
                hp=15,
                max_hp=15,
                ac=14,
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
                visibility_scope=VisibilityScope(visibility=Visibility.PUBLIC),
            ),
            "dead-goblin": NpcState(
                actor_id="dead-goblin",
                name="Dead Goblin",
                role=ActorRole.NPC,
                hp=0,
                max_hp=7,
                ac=12,
                disposition="hostile",
                alive=False,
                visibility_scope=VisibilityScope(visibility=Visibility.PUBLIC),
            ),
        },
        objectives=[],
        flags={},
    )


class TestAttackValidator:
    def test_valid_attack_against_npc(self, base_state: GameState) -> None:
        validator = AttackValidator()
        action = AttackAction(type=ActionType.ATTACK, target_id="goblin-1")

        result = validator.validate(action, "player-1", base_state)

        assert result.valid is True
        assert len(result.errors) == 0

    def test_attack_nonexistent_target(self, base_state: GameState) -> None:
        validator = AttackValidator()
        action = AttackAction(type=ActionType.ATTACK, target_id="nonexistent")

        result = validator.validate(action, "player-1", base_state)

        assert result.valid is False
        assert any("does not exist" in e for e in result.errors)

    def test_attack_dead_target(self, base_state: GameState) -> None:
        validator = AttackValidator()
        action = AttackAction(type=ActionType.ATTACK, target_id="dead-goblin")

        result = validator.validate(action, "player-1", base_state)

        assert result.valid is False
        assert any("not alive" in e for e in result.errors)

    def test_attack_self(self, base_state: GameState) -> None:
        validator = AttackValidator()
        action = AttackAction(type=ActionType.ATTACK, target_id="player-1")

        result = validator.validate(action, "player-1", base_state)

        assert result.valid is False
        assert any("yourself" in e.lower() for e in result.errors)

    def test_attack_with_nonexistent_actor(self, base_state: GameState) -> None:
        validator = AttackValidator()
        action = AttackAction(type=ActionType.ATTACK, target_id="goblin-1")

        result = validator.validate(action, "nonexistent-actor", base_state)

        assert result.valid is False
        assert any("does not exist" in e for e in result.errors)

    def test_dead_actor_cannot_attack(self, base_state: GameState) -> None:
        validator = AttackValidator()
        action = AttackAction(type=ActionType.ATTACK, target_id="goblin-1")

        result = validator.validate(action, "dead-goblin", base_state)

        assert result.valid is False
        assert any("cannot act" in e for e in result.errors)

    def test_attack_another_player(self, base_state: GameState) -> None:
        validator = AttackValidator()
        action = AttackAction(type=ActionType.ATTACK, target_id="player-2")

        result = validator.validate(action, "player-1", base_state)

        assert result.valid is True


class TestMoveValidator:
    def test_valid_move(self, base_state: GameState) -> None:
        validator = MoveValidator()
        action = MoveAction(type=ActionType.MOVE, movement_path=["A1", "A2", "A3"])

        result = validator.validate(action, "player-1", base_state)

        assert result.valid is True

    def test_move_exceeds_budget(self, base_state: GameState) -> None:
        validator = MoveValidator()
        action = MoveAction(
            type=ActionType.MOVE,
            movement_path=["A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8", "A9"],
        )

        result = validator.validate(action, "player-1", base_state)

        assert result.valid is False
        assert any("exceeds maximum" in e for e in result.errors)

    def test_move_with_single_step(self, base_state: GameState) -> None:
        validator = MoveValidator()
        action = MoveAction(type=ActionType.MOVE, movement_path=["A1"])

        result = validator.validate(action, "player-1", base_state)

        assert result.valid is True


class TestDefendValidator:
    def test_valid_defend_guard(self, base_state: GameState) -> None:
        validator = DefendValidator()
        action = DefendAction(type=ActionType.DEFEND, stance="guard")

        result = validator.validate(action, "player-1", base_state)

        assert result.valid is True

    def test_valid_defend_dodge(self, base_state: GameState) -> None:
        validator = DefendValidator()
        action = DefendAction(type=ActionType.DEFEND, stance="dodge")

        result = validator.validate(action, "player-1", base_state)

        assert result.valid is True

    def test_valid_defend_brace(self, base_state: GameState) -> None:
        validator = DefendValidator()
        action = DefendAction(type=ActionType.DEFEND, stance="brace")

        result = validator.validate(action, "player-1", base_state)

        assert result.valid is True


class TestInspectValidator:
    def test_inspect_with_target(self, base_state: GameState) -> None:
        validator = InspectValidator()
        action = InspectAction(type=ActionType.INSPECT, target_id="goblin-1")

        result = validator.validate(action, "player-1", base_state)

        assert result.valid is True

    def test_inspect_with_location(self, base_state: GameState) -> None:
        validator = InspectValidator()
        action = InspectAction(type=ActionType.INSPECT, location_id="room-entrance")

        result = validator.validate(action, "player-1", base_state)

        assert result.valid is True

    def test_inspect_with_both(self, base_state: GameState) -> None:
        validator = InspectValidator()
        action = InspectAction(
            type=ActionType.INSPECT,
            target_id="goblin-1",
            location_id="room-entrance",
            detail="Look for traps",
        )

        result = validator.validate(action, "player-1", base_state)

        assert result.valid is True


class TestCastSpellValidator:
    def test_valid_cast_spell(self, base_state: GameState) -> None:
        validator = CastSpellValidator()
        action = CastSpellBasicAction(
            type=ActionType.CAST_SPELL_BASIC,
            spell_id="magic-missile",
            target_id="goblin-1",
        )

        result = validator.validate(action, "player-1", base_state)

        assert result.valid is True

    def test_cast_spell_without_target(self, base_state: GameState) -> None:
        validator = CastSpellValidator()
        action = CastSpellBasicAction(
            type=ActionType.CAST_SPELL_BASIC,
            spell_id="shield",
        )

        result = validator.validate(action, "player-1", base_state)

        assert result.valid is True

    def test_cast_spell_on_dead_target_allowed(self, base_state: GameState) -> None:
        """Spells can target dead creatures (e.g., for resurrection)."""
        validator = CastSpellValidator()
        action = CastSpellBasicAction(
            type=ActionType.CAST_SPELL_BASIC,
            spell_id="revivify",
            target_id="dead-goblin",
        )

        result = validator.validate(action, "player-1", base_state)

        assert result.valid is True

    def test_cast_spell_on_nonexistent_target(self, base_state: GameState) -> None:
        validator = CastSpellValidator()
        action = CastSpellBasicAction(
            type=ActionType.CAST_SPELL_BASIC,
            spell_id="fire-bolt",
            target_id="nonexistent",
        )

        result = validator.validate(action, "player-1", base_state)

        assert result.valid is False
        assert any("does not exist" in e for e in result.errors)


class TestMoveAndAttackValidator:
    def test_valid_move_and_attack(self, base_state: GameState) -> None:
        validator = MoveAndAttackValidator()
        action = MoveAndAttackAction(
            type=ActionType.MOVE_AND_ATTACK,
            movement_path=["A1", "A2"],
            target_id="goblin-1",
        )

        result = validator.validate(action, "player-1", base_state)

        assert result.valid is True

    def test_move_and_attack_exceeds_budget(self, base_state: GameState) -> None:
        validator = MoveAndAttackValidator()
        action = MoveAndAttackAction(
            type=ActionType.MOVE_AND_ATTACK,
            movement_path=["A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8", "A9"],
            target_id="goblin-1",
        )

        result = validator.validate(action, "player-1", base_state)

        assert result.valid is False
        assert any("exceeds maximum" in e.lower() for e in result.errors)

    def test_move_and_attack_invalid_target(self, base_state: GameState) -> None:
        validator = MoveAndAttackValidator()
        action = MoveAndAttackAction(
            type=ActionType.MOVE_AND_ATTACK,
            movement_path=["A1", "A2"],
            target_id="nonexistent",
        )

        result = validator.validate(action, "player-1", base_state)

        assert result.valid is False
        assert any("does not exist" in e for e in result.errors)

    def test_move_and_attack_self(self, base_state: GameState) -> None:
        validator = MoveAndAttackValidator()
        action = MoveAndAttackAction(
            type=ActionType.MOVE_AND_ATTACK,
            movement_path=["A1", "A2"],
            target_id="player-1",
        )

        result = validator.validate(action, "player-1", base_state)

        assert result.valid is False
        assert any("yourself" in e.lower() for e in result.errors)
