from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from shared_schemas.events import (
    ActionResolvedEvent,
    ActionResolvedPayload,
    DiceRollRecord,
    GameEvent,
    StatePatchRecord,
)
from shared_schemas.examples import (
    build_example_action_proposed_event,
    build_example_action_resolved_event,
    build_example_action_validated_event,
    build_example_dice_rolled_event,
    build_example_discussion_closed_event,
    build_example_discussion_opened_event,
    build_example_message_created_event,
    build_example_narration_emitted_event,
    build_example_scene_started_event,
    build_example_session_started_event,
    build_example_state_updated_event,
    build_example_turn_ended_event,
)
from shared_schemas.state import GameState


@pytest.mark.parametrize(
    "payload",
    [
        build_example_session_started_event().model_dump(mode="json"),
        build_example_scene_started_event().model_dump(mode="json"),
        build_example_discussion_opened_event().model_dump(mode="json"),
        build_example_discussion_closed_event().model_dump(mode="json"),
        build_example_message_created_event().model_dump(mode="json"),
        build_example_action_proposed_event().model_dump(mode="json"),
        build_example_action_validated_event().model_dump(mode="json"),
        build_example_dice_rolled_event().model_dump(mode="json"),
        build_example_action_resolved_event().model_dump(mode="json"),
        build_example_state_updated_event().model_dump(mode="json"),
        build_example_narration_emitted_event().model_dump(mode="json"),
        build_example_turn_ended_event().model_dump(mode="json"),
    ],
)
def test_required_phase_one_events_validate(payload: dict[str, Any]) -> None:
    event = TypeAdapter(GameEvent).validate_python(payload)
    assert event.session_id == "session_001"


@pytest.mark.parametrize("field_name", ["trace_id", "correlation_id"])
def test_game_event_requires_traceability_fields(field_name: str) -> None:
    payload = build_example_action_proposed_event().model_dump(mode="json")
    payload.pop(field_name)

    with pytest.raises(ValidationError):
        TypeAdapter(GameEvent).validate_python(payload)


class TestActionResolvedEvent:
    def test_action_resolved_event_validates(self) -> None:
        event = build_example_action_resolved_event()
        assert event.event_type == "action.resolved"
        assert event.payload.success is True
        assert event.payload.hit is True
        assert event.payload.damage == 8
        assert len(event.payload.dice_rolls) == 2
        assert len(event.payload.state_patches) == 1

    def test_action_resolved_with_miss(self) -> None:
        now = datetime.now()
        event = ActionResolvedEvent(
            id="event_miss",
            session_id="session_001",
            turn_number=1,
            trace_id="trace_001",
            correlation_id="corr_001",
            created_at=now,
            payload=ActionResolvedPayload(
                actor_id="player_1",
                action_type="attack",
                success=True,
                description="The attack misses.",
                dice_rolls=[
                    DiceRollRecord(die="d20", value=5, modifier=3, total=8, created_at=now)
                ],
                state_patches=[],
                hit=False,
                damage=None,
                created_at=now,
            ),
        )
        assert event.payload.hit is False
        assert event.payload.damage is None
        assert len(event.payload.state_patches) == 0

    def test_action_resolved_without_combat(self) -> None:
        now = datetime.now()
        event = ActionResolvedEvent(
            id="event_move",
            session_id="session_001",
            turn_number=1,
            trace_id="trace_001",
            correlation_id="corr_001",
            created_at=now,
            payload=ActionResolvedPayload(
                actor_id="player_1",
                action_type="move",
                success=True,
                description="The fighter moves to B5.",
                dice_rolls=[],
                state_patches=[
                    StatePatchRecord(
                        patch_type="position",
                        target_id="player_1",
                        field="position",
                        old_value={"node_id": "B3"},
                        new_value={"node_id": "B5"},
                        created_at=now,
                    )
                ],
                hit=None,
                damage=None,
                created_at=now,
            ),
        )
        assert event.payload.hit is None
        assert len(event.payload.state_patches) == 1


class TestStatePatchRecord:
    def test_state_patch_with_various_types(self) -> None:
        now = datetime.now()

        int_patch = StatePatchRecord(
            patch_type="damage", target_id="npc_1", field="hp", old_value=12, new_value=5, created_at=now
        )
        assert int_patch.old_value == 12
        assert int_patch.new_value == 5

        bool_patch = StatePatchRecord(
            patch_type="death", target_id="npc_1", field="alive", old_value=True, new_value=False, created_at=now
        )
        assert bool_patch.old_value is True
        assert bool_patch.new_value is False

        list_patch = StatePatchRecord(
            patch_type="status",
            target_id="player_1",
            field="status_effects",
            old_value=[],
            new_value=["poisoned"],
            created_at=now,
        )
        assert list_patch.new_value == ["poisoned"]

        dict_patch = StatePatchRecord(
            patch_type="position",
            target_id="player_1",
            field="position",
            old_value={"node_id": "A1", "zone_id": "dungeon"},
            new_value={"node_id": "A2", "zone_id": "dungeon"},
            created_at=now,
        )
        assert dict_patch.new_value["node_id"] == "A2"


class TestDiceRollRecord:
    def test_dice_roll_requires_positive_value(self) -> None:
        with pytest.raises(ValidationError):
            DiceRollRecord(
                die="d20", value=0, modifier=3, total=3, created_at=datetime.now()
            )

    def test_dice_roll_allows_negative_modifier(self) -> None:
        now = datetime.now()
        roll = DiceRollRecord(die="d20", value=10, modifier=-2, total=8, created_at=now)
        assert roll.modifier == -2
        assert roll.total == 8


class TestGameStateRoundTrip:
    def test_game_state_serialization_roundtrip(self) -> None:
        from shared_schemas.examples import build_example_game_state

        original = build_example_game_state()
        serialized = original.model_dump(mode="json")
        deserialized = GameState.model_validate(serialized)

        assert deserialized.campaign_id == original.campaign_id
        assert deserialized.session_id == original.session_id
        assert deserialized.scene.scene_id == original.scene.scene_id
        assert len(deserialized.characters) == len(original.characters)
        assert len(deserialized.npcs) == len(original.npcs)

    def test_game_state_preserves_nested_objects(self) -> None:
        from shared_schemas.examples import build_example_game_state

        original = build_example_game_state()
        serialized = original.model_dump(mode="json")
        deserialized = GameState.model_validate(serialized)

        original_char = original.characters["char_fighter"]
        deserialized_char = deserialized.characters["char_fighter"]

        assert deserialized_char.hp == original_char.hp
        assert deserialized_char.position is not None
        assert deserialized_char.position.node_id == original_char.position.node_id
