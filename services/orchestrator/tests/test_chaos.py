"""Chaos tests for orchestrator - error handling and edge case scenarios."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from shared_schemas.actions import AttackAction, DefendAction, PlayerTurn
from shared_schemas.enums import ActionType, ScenePhase
from shared_schemas.state import GameState

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "agent-runtime"))

from app.service_integration import (
    InvokeAgentResponse,
    ResolveActionResponse,
    ValidateActionResponse,
    CreateMessageResponse,
    DiceRoll,
    StatePatch,
    get_fallback_turn,
    apply_state_patches,
)


class TestMalformedAgentResponse:
    """Test handling of malformed JSON from agent via PlayerTurn validation."""

    def test_invalid_json_raises_validation_error(self) -> None:
        """Invalid JSON should not parse as PlayerTurn."""
        from pydantic import ValidationError

        with pytest.raises((json.JSONDecodeError, ValidationError)):
            data = json.loads("this is not json {][[")
            PlayerTurn.model_validate(data)

    def test_partial_json_raises_error(self) -> None:
        """Truncated JSON should not parse."""
        with pytest.raises(json.JSONDecodeError):
            json.loads('{"speech": "Hello')

    def test_empty_string_raises_error(self) -> None:
        """Empty string should not parse as JSON."""
        with pytest.raises(json.JSONDecodeError):
            json.loads("")

    def test_valid_json_missing_required_content(self) -> None:
        """Turn with only thought but no visible output should fail."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            PlayerTurn.model_validate({"thought": "I am thinking..."})

    def test_valid_player_turn_parses(self) -> None:
        """Valid PlayerTurn JSON should parse correctly."""
        data = {
            "speech": "Hello!",
            "action": {"type": "defend", "stance": "guard"},
        }
        turn = PlayerTurn.model_validate(data)
        assert turn.speech == "Hello!"
        assert turn.action is not None

    def test_malformed_action_raises_error(self) -> None:
        """Invalid action type should raise validation error."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            PlayerTurn.model_validate({
                "speech": "Attack!",
                "action": {"type": "invalid_action_type", "target": "enemy"},
            })


class TestAgentTimeoutBehavior:
    """Test behavior when agent invocation times out or fails."""

    def test_fallback_turn_is_valid(self) -> None:
        """Fallback turn should be a valid PlayerTurn."""
        fallback = get_fallback_turn()
        assert fallback.action is not None
        assert fallback.action.type == ActionType.DEFEND
        assert fallback.speech is not None
        assert fallback.thought is not None

    def test_fallback_action_is_defend(self) -> None:
        """Fallback should use defensive action."""
        fallback = get_fallback_turn()
        assert isinstance(fallback.action, DefendAction)
        assert fallback.action.stance == "guard"

    def test_invoke_agent_response_error_handling(self) -> None:
        """InvokeAgentResponse should properly report errors."""
        error_response = InvokeAgentResponse(
            success=False,
            turn=None,
            error="Connection timeout after 60s",
        )
        assert error_response.success is False
        assert error_response.error is not None
        assert error_response.turn is None


class TestInvalidActionProposal:
    """Test handling of invalid action proposals."""

    def test_validation_response_with_errors(self) -> None:
        """ValidateActionResponse should carry error messages."""
        response = ValidateActionResponse(
            valid=False,
            errors=["Target does not exist", "Actor cannot act"],
            warnings=["Low mana"],
        )
        assert response.valid is False
        assert len(response.errors) == 2
        assert len(response.warnings) == 1

    def test_validation_response_success(self) -> None:
        """ValidateActionResponse should report success correctly."""
        response = ValidateActionResponse(valid=True, errors=[], warnings=[])
        assert response.valid is True
        assert len(response.errors) == 0

    def test_action_against_dead_target(self) -> None:
        """Validate that action against dead target produces error."""
        response = ValidateActionResponse(
            valid=False,
            errors=["Target 'goblin-1' is not alive"],
        )
        assert response.valid is False
        assert "not alive" in response.errors[0]


class TestStatePatchCorruption:
    """Test handling of corrupted or invalid state patches."""

    def test_patch_with_invalid_target_is_ignored(self, mvp_state: GameState) -> None:
        """Patches for non-existent entities should be silently ignored."""
        original_state = mvp_state.model_copy()
        patches = [
            StatePatch(
                patch_type="damage",
                target_id="nonexistent-entity-xyz",
                field="hp",
                old_value=100,
                new_value=0,
            ),
        ]
        updated = apply_state_patches(mvp_state, patches)
        assert updated.characters == original_state.characters

    def test_patch_with_unsupported_field(self, mvp_state: GameState) -> None:
        """Patches with unknown field should not raise."""
        char_id = list(mvp_state.characters.keys())[0]
        patches = [
            StatePatch(
                patch_type="unknown",
                target_id=char_id,
                field="unknown_field",
                old_value="old",
                new_value="new",
            ),
        ]
        updated = apply_state_patches(mvp_state, patches)
        assert updated.characters[char_id].hp == mvp_state.characters[char_id].hp

    def test_multiple_patches_partial_failure(self, mvp_state: GameState) -> None:
        """Valid patches should apply even if some fail."""
        char_id = list(mvp_state.characters.keys())[0]
        original_hp = mvp_state.characters[char_id].hp
        
        patches = [
            StatePatch(
                patch_type="damage",
                target_id="nonexistent",
                field="hp",
                old_value=10,
                new_value=5,
            ),
            StatePatch(
                patch_type="damage",
                target_id=char_id,
                field="hp",
                old_value=original_hp,
                new_value=original_hp - 3,
            ),
        ]
        updated = apply_state_patches(mvp_state, patches)
        assert updated.characters[char_id].hp == original_hp - 3


class TestResolutionFailure:
    """Test handling of resolution failures."""

    def test_resolution_response_failure(self) -> None:
        """ResolveActionResponse should properly report failures."""
        response = ResolveActionResponse(
            success=False,
            action_type=ActionType.ATTACK,
            description="Failed to resolve action: internal error",
            dice_rolls=[],
            state_patches=[],
        )
        assert response.success is False
        assert "Failed" in response.description

    def test_resolution_with_empty_dice_rolls(self) -> None:
        """Defend action resolution has no dice rolls."""
        response = ResolveActionResponse(
            success=True,
            action_type=ActionType.DEFEND,
            description="Takes defensive stance",
            dice_rolls=[],
            state_patches=[],
        )
        assert response.success is True
        assert len(response.dice_rolls) == 0


class TestDuplicateEventHandling:
    """Test that duplicate events are handled correctly."""

    def test_idempotent_state_patch(self, mvp_state: GameState) -> None:
        """Applying same patch twice should not double the effect."""
        char_id = list(mvp_state.characters.keys())[0]
        original_hp = mvp_state.characters[char_id].hp
        
        patch = StatePatch(
            patch_type="damage",
            target_id=char_id,
            field="hp",
            old_value=original_hp,
            new_value=original_hp - 5,
        )

        state_after_first = apply_state_patches(mvp_state, [patch])
        assert state_after_first.characters[char_id].hp == original_hp - 5

        state_after_second = apply_state_patches(state_after_first, [patch])
        assert state_after_second.characters[char_id].hp == original_hp - 5


class TestCommunicationServiceFailure:
    """Test handling of communication service failures."""

    def test_create_message_failure_response(self) -> None:
        """CreateMessageResponse should properly report failures."""
        response = CreateMessageResponse(
            success=False,
            message=None,
            error="Service unavailable",
        )
        assert response.success is False
        assert response.error is not None
        assert response.message is None


class TestEdgeCaseInputs:
    """Test edge case inputs that might cause issues."""

    def test_empty_dice_roll_list(self) -> None:
        """Resolution with no dice rolls should work."""
        response = ResolveActionResponse(
            success=True,
            action_type=ActionType.INSPECT,
            description="Inspected the altar",
            dice_rolls=[],
            state_patches=[],
        )
        assert response.success is True
        assert response.hit is None
        assert response.damage is None

    def test_very_large_damage_value(self, mvp_state: GameState) -> None:
        """Large damage values should be handled."""
        npc_id = list(mvp_state.npcs.keys())[0]
        patches = [
            StatePatch(
                patch_type="damage",
                target_id=npc_id,
                field="hp",
                old_value=mvp_state.npcs[npc_id].hp,
                new_value=-9999,
            ),
        ]
        updated = apply_state_patches(mvp_state, patches)
        assert updated.npcs[npc_id].hp == -9999

    def test_player_turn_with_unicode(self) -> None:
        """PlayerTurn should handle unicode characters."""
        turn = PlayerTurn.model_validate({
            "speech": "¡Hola! 你好! مرحبا! 🗡️",
            "action": {"type": "defend", "stance": "guard"},
        })
        assert turn.speech is not None
        assert "🗡️" in turn.speech

    def test_player_turn_with_very_long_speech(self) -> None:
        """PlayerTurn should handle long speech."""
        long_speech = "A" * 10000
        turn = PlayerTurn.model_validate({
            "speech": long_speech,
        })
        assert turn.speech == long_speech


class TestScenePhaseValidation:
    """Test scene phase validation edge cases."""

    def test_all_phases_are_defined(self) -> None:
        """All expected phases should exist."""
        expected_phases = [
            ScenePhase.SCENE_INTRO,
            ScenePhase.DISCUSSION,
            ScenePhase.ACTION_COMMIT,
            ScenePhase.RESOLUTION,
            ScenePhase.NARRATION,
            ScenePhase.REACTION,
            ScenePhase.TURN_END,
        ]
        for phase in expected_phases:
            assert phase is not None

    def test_phase_values_are_strings(self) -> None:
        """Phase enum values should be strings."""
        for phase in ScenePhase:
            assert isinstance(phase.value, str)
