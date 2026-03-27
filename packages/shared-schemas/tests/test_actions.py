from __future__ import annotations

from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from shared_schemas.actions import ActionUnion, PlayerTurn
from shared_schemas.enums import ActionType


@pytest.mark.parametrize(
    ("payload", "expected_type"),
    [
        ({"type": "attack", "target_id": "npc_1"}, "attack"),
        ({"type": "move", "movement_path": ["A1", "A2"]}, "move"),
        (
            {
                "type": "move_and_attack",
                "movement_path": ["A1", "A2"],
                "target_id": "npc_1",
            },
            "move_and_attack",
        ),
        ({"type": "defend", "stance": "brace"}, "defend"),
        ({"type": "inspect", "target_id": "altar_1"}, "inspect"),
        (
            {
                "type": "cast_spell_basic",
                "spell_id": "spell_magic_missile",
                "target_id": "npc_1",
            },
            "cast_spell_basic",
        ),
    ],
)
def test_action_union_accepts_all_public_subtypes(payload: dict[str, Any], expected_type: str) -> None:
    action = TypeAdapter(ActionUnion).validate_python(payload)
    assert action.type == expected_type


def test_action_union_rejects_unknown_type() -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(ActionUnion).validate_python({"type": "sing", "target_id": "npc_1"})


def test_player_turn_accepts_legacy_aliases() -> None:
    turn = PlayerTurn.model_validate(
        {
            "private_thought": "This should map to thought.",
            "in_character_speech": "For glory.",
            "action": {"type": ActionType.ATTACK, "target_id": "npc_1"},
        }
    )

    assert turn.thought == "This should map to thought."
    assert turn.speech == "For glory."
    assert turn.action is not None
    assert turn.action.type == "attack"


def test_player_turn_requires_visible_output_or_action() -> None:
    with pytest.raises(ValidationError):
        PlayerTurn.model_validate({"thought": "I keep this to myself."})


class TestPlayerTurnEdgeCases:
    def test_player_turn_with_speech_only(self) -> None:
        turn = PlayerTurn.model_validate({"speech": "Hello everyone!"})
        assert turn.speech == "Hello everyone!"
        assert turn.action is None
        assert turn.table_talk is None

    def test_player_turn_with_table_talk_only(self) -> None:
        turn = PlayerTurn.model_validate({"table_talk": "Focus the shaman!"})
        assert turn.table_talk == "Focus the shaman!"
        assert turn.action is None
        assert turn.speech is None

    def test_player_turn_with_action_only(self) -> None:
        turn = PlayerTurn.model_validate({"action": {"type": "defend", "stance": "guard"}})
        assert turn.action is not None
        assert turn.action.type == ActionType.DEFEND
        assert turn.speech is None

    def test_player_turn_with_all_fields(self) -> None:
        turn = PlayerTurn.model_validate({
            "thought": "Private reasoning",
            "speech": "In character speech",
            "table_talk": "Tactical advice",
            "action": {"type": "attack", "target_id": "goblin_1"},
        })
        assert turn.thought == "Private reasoning"
        assert turn.speech == "In character speech"
        assert turn.table_talk == "Tactical advice"
        assert turn.action is not None

    def test_player_turn_empty_strings_treated_as_none(self) -> None:
        turn = PlayerTurn.model_validate({
            "speech": "Hello",
            "thought": "",
        })
        assert turn.speech == "Hello"

    def test_player_turn_rejects_invalid_action_type(self) -> None:
        with pytest.raises(ValidationError):
            PlayerTurn.model_validate({
                "speech": "I attack!",
                "action": {"type": "invalid_action", "target_id": "npc_1"},
            })


class TestInspectActionValidation:
    def test_inspect_requires_target_or_location(self) -> None:
        with pytest.raises(ValidationError):
            TypeAdapter(ActionUnion).validate_python({"type": "inspect"})

    def test_inspect_with_target_id(self) -> None:
        action = TypeAdapter(ActionUnion).validate_python({
            "type": "inspect",
            "target_id": "chest_1",
        })
        assert action.target_id == "chest_1"
        assert action.location_id is None

    def test_inspect_with_location_id(self) -> None:
        action = TypeAdapter(ActionUnion).validate_python({
            "type": "inspect",
            "location_id": "room_entrance",
        })
        assert action.location_id == "room_entrance"
        assert action.target_id is None

    def test_inspect_with_both(self) -> None:
        action = TypeAdapter(ActionUnion).validate_python({
            "type": "inspect",
            "target_id": "altar",
            "location_id": "temple_room",
            "detail": "Check for traps",
        })
        assert action.target_id == "altar"
        assert action.location_id == "temple_room"
        assert action.detail == "Check for traps"


class TestMoveActionValidation:
    def test_move_requires_non_empty_path(self) -> None:
        with pytest.raises(ValidationError):
            TypeAdapter(ActionUnion).validate_python({
                "type": "move",
                "movement_path": [],
            })

    def test_move_with_valid_path(self) -> None:
        action = TypeAdapter(ActionUnion).validate_python({
            "type": "move",
            "movement_path": ["A1", "A2", "A3"],
        })
        assert len(action.movement_path) == 3


class TestCastSpellAction:
    def test_cast_spell_requires_spell_id(self) -> None:
        with pytest.raises(ValidationError):
            TypeAdapter(ActionUnion).validate_python({
                "type": "cast_spell_basic",
                "target_id": "npc_1",
            })

    def test_cast_spell_with_slot_level(self) -> None:
        action = TypeAdapter(ActionUnion).validate_python({
            "type": "cast_spell_basic",
            "spell_id": "fireball",
            "target_id": "npc_group",
            "spell_slot_level": 3,
        })
        assert action.spell_slot_level == 3

    def test_cast_spell_rejects_negative_slot_level(self) -> None:
        with pytest.raises(ValidationError):
            TypeAdapter(ActionUnion).validate_python({
                "type": "cast_spell_basic",
                "spell_id": "fireball",
                "spell_slot_level": -1,
            })
