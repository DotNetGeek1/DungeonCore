from __future__ import annotations

from pydantic import TypeAdapter

from shared_schemas import (
    EXAMPLE_API_PAYLOADS,
    EXAMPLE_EVENTS,
    EXAMPLE_GAME_STATE,
    EXAMPLE_PERSISTENCE_PAYLOADS,
    EXAMPLE_PLAYER_TURN,
)
from shared_schemas.actions import PlayerTurn
from shared_schemas.api import CreateSessionResponse
from shared_schemas.events import GameEvent
from shared_schemas.persistence import ActionRecord, StateSnapshotRecord
from shared_schemas.state import GameState


def test_examples_are_stable_and_parseable() -> None:
    state = GameState.model_validate(EXAMPLE_GAME_STATE)
    turn = PlayerTurn.model_validate(EXAMPLE_PLAYER_TURN)
    create_session = CreateSessionResponse.model_validate(EXAMPLE_API_PAYLOADS["create_session_response"])
    event = TypeAdapter(GameEvent).validate_python(EXAMPLE_EVENTS["action_proposed"])
    snapshot = StateSnapshotRecord.model_validate(EXAMPLE_PERSISTENCE_PAYLOADS["state_snapshot_record"])
    action_record = ActionRecord.model_validate(EXAMPLE_PERSISTENCE_PAYLOADS["action_record"])

    assert state.session_id == "session_001"
    assert turn.action is not None
    assert create_session.session.status == "created"
    assert event.event_type == "action.proposed"
    assert snapshot.scene_id == "scene_bridge"
    assert action_record.actor_id == "char_fighter"
