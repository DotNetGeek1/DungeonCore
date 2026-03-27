from __future__ import annotations

import pytest
from pydantic import ValidationError

from shared_schemas.api import CreateSessionRequest, GetSessionStateResponse
from shared_schemas.context import AgentContext
from shared_schemas.examples import (
    build_example_action_record,
    build_example_agent_context,
    build_example_create_session_request,
    build_example_event_history_query,
    build_example_game_state,
    build_example_get_session_state_response,
    build_example_memory_entry,
    build_example_state_snapshot_record,
    build_example_table_message,
)
from shared_schemas.memory import MemoryEntry
from shared_schemas.messages import TableMessage
from shared_schemas.persistence import ActionRecord, EventHistoryQuery, StateSnapshotRecord
from shared_schemas.state import GameState


def test_game_state_example_validates() -> None:
    state = GameState.model_validate(build_example_game_state().model_dump(mode="json"))
    assert state.turn.active_actor_id == "char_fighter"


def test_table_message_requires_text() -> None:
    payload = build_example_table_message().model_dump(mode="json")
    payload["text"] = ""

    with pytest.raises(ValidationError):
        TableMessage.model_validate(payload)


def test_memory_entry_validates_importance_range() -> None:
    payload = build_example_memory_entry().model_dump(mode="json")
    payload["importance"] = 11

    with pytest.raises(ValidationError):
        MemoryEntry.model_validate(payload)


def test_agent_context_example_validates() -> None:
    context = AgentContext.model_validate(build_example_agent_context().model_dump(mode="json"))
    assert context.identity.actor_id == "char_fighter"
    assert len(context.allowed_actions) >= 1


def test_api_request_and_response_examples_validate() -> None:
    request = CreateSessionRequest.model_validate(build_example_create_session_request().model_dump(mode="json"))
    response = GetSessionStateResponse.model_validate(
        build_example_get_session_state_response().model_dump(mode="json")
    )

    assert request.campaign_id == "campaign_blackstone"
    assert response.session_id == "session_001"


def test_persistence_records_validate() -> None:
    query = EventHistoryQuery.model_validate(build_example_event_history_query().model_dump(mode="json"))
    snapshot = StateSnapshotRecord.model_validate(build_example_state_snapshot_record().model_dump(mode="json"))
    action_record = ActionRecord.model_validate(build_example_action_record().model_dump(mode="json"))

    assert query.limit == 25
    assert snapshot.turn_number == 1
    assert action_record.status == "validated"
