from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from .actions import ActionUnion, PlayerTurn
from .api import (
    ActionSubmissionRequest,
    ActionSubmissionResponse,
    CreateSessionRequest,
    CreateSessionResponse,
    GetEventHistoryResponse,
    GetSessionStateResponse,
    GetVisibleMessagesResponse,
    HealthcheckResponse,
    OperatorCommandRequest,
    OperatorCommandResponse,
    SessionStateResponse,
    WebSocketEventEnvelope,
)
from .context import AgentContext
from .events import GameEvent
from .memory import MemoryEntry
from .messages import TableMessage
from .persistence import ActionRecord, EventHistoryQuery, StateSnapshotRecord
from .state import GameState


def export_schema_bundle() -> dict[str, Any]:
    return {
        "GameState": GameState.model_json_schema(),
        "PlayerTurn": PlayerTurn.model_json_schema(),
        "ActionUnion": TypeAdapter(ActionUnion).json_schema(),
        "GameEvent": TypeAdapter(GameEvent).json_schema(),
        "TableMessage": TableMessage.model_json_schema(),
        "MemoryEntry": MemoryEntry.model_json_schema(),
        "EventHistoryQuery": EventHistoryQuery.model_json_schema(),
        "StateSnapshotRecord": StateSnapshotRecord.model_json_schema(),
        "ActionRecord": ActionRecord.model_json_schema(),
        "AgentContext": AgentContext.model_json_schema(),
        "CreateSessionRequest": CreateSessionRequest.model_json_schema(),
        "CreateSessionResponse": CreateSessionResponse.model_json_schema(),
        "GetSessionStateResponse": GetSessionStateResponse.model_json_schema(),
        "GetEventHistoryResponse": GetEventHistoryResponse.model_json_schema(),
        "GetVisibleMessagesResponse": GetVisibleMessagesResponse.model_json_schema(),
        "OperatorCommandRequest": OperatorCommandRequest.model_json_schema(),
        "OperatorCommandResponse": OperatorCommandResponse.model_json_schema(),
        "ActionSubmissionRequest": ActionSubmissionRequest.model_json_schema(),
        "ActionSubmissionResponse": ActionSubmissionResponse.model_json_schema(),
        "WebSocketEventEnvelope": WebSocketEventEnvelope.model_json_schema(),
        "SessionStateResponse": SessionStateResponse.model_json_schema(),
        "HealthcheckResponse": HealthcheckResponse.model_json_schema(),
    }


def write_schema_bundle(output_dir: str | Path) -> Path:
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    output_path = destination / "shared-schemas.json"
    output_path.write_text(
        json.dumps(export_schema_bundle(), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return output_path


if __name__ == "__main__":
    target = Path(__file__).resolve().parents[2] / "schemas"
    path = write_schema_bundle(target)
    print(path)
