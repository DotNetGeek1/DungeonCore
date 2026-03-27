from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Path, WebSocket, WebSocketDisconnect

from shared_schemas.api import WebSocketEventEnvelope
from shared_schemas.enums import ScenePhase, Visibility
from shared_schemas.events import (
    SessionStartedEvent,
    SessionStartedPayload,
)
from shared_schemas.state import (
    GameState,
    ObjectiveState,
    SceneState,
    TurnState,
    VisibilityScope,
)

router = APIRouter()


class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: dict[str, list[WebSocket]] = {}
        self._sequence_counters: dict[str, int] = {}

    async def connect(self, session_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        if session_id not in self.active_connections:
            self.active_connections[session_id] = []
            self._sequence_counters[session_id] = 0
        self.active_connections[session_id].append(websocket)

    def disconnect(self, session_id: str, websocket: WebSocket) -> None:
        if session_id in self.active_connections:
            self.active_connections[session_id].remove(websocket)
            if not self.active_connections[session_id]:
                del self.active_connections[session_id]
                del self._sequence_counters[session_id]

    async def broadcast_to_session(self, session_id: str, envelope: WebSocketEventEnvelope) -> None:
        if session_id not in self.active_connections:
            return

        message = envelope.model_dump_json()
        disconnected: list[WebSocket] = []

        for connection in self.active_connections[session_id]:
            try:
                await connection.send_text(message)
            except Exception:
                disconnected.append(connection)

        for conn in disconnected:
            self.disconnect(session_id, conn)

    def get_next_sequence(self, session_id: str) -> int:
        if session_id not in self._sequence_counters:
            self._sequence_counters[session_id] = 0
        seq = self._sequence_counters[session_id]
        self._sequence_counters[session_id] += 1
        return seq


manager = ConnectionManager()


def _create_minimal_state(session_id: str, campaign_id: str) -> GameState:
    return GameState(
        campaign_id=campaign_id,
        session_id=session_id,
        scene=SceneState(
            scene_id="welcome",
            name="Connected",
            summary="WebSocket connection established.",
            turn_number=0,
            active_actor_id=None,
            phase=ScenePhase.SCENE_INTRO,
        ),
        turn=TurnState(
            turn_number=0,
            round_number=1,
            active_actor_id=None,
            phase=ScenePhase.SCENE_INTRO,
            discussion_open=False,
            max_discussion_messages=0,
            remaining_discussion_messages=0,
        ),
        characters={},
        npcs={},
        objectives=[],
        flags={},
    )


@router.websocket("/sessions/{session_id}/stream")
async def session_stream(
    websocket: WebSocket,
    session_id: Annotated[str, Path(description="The session identifier")],
) -> None:
    await manager.connect(session_id, websocket)

    trace_id = str(uuid.uuid4())
    correlation_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    campaign_id = "connected"

    welcome_event = SessionStartedEvent(
        id=str(uuid.uuid4()),
        event_type="session.started",
        session_id=session_id,
        turn_number=0,
        trace_id=trace_id,
        correlation_id=correlation_id,
        created_at=now,
        payload=SessionStartedPayload(
            session_id=session_id,
            campaign_id=campaign_id,
            started_by=None,
            initial_state=_create_minimal_state(session_id, campaign_id),
            created_at=now,
        ),
    )

    envelope = WebSocketEventEnvelope(
        session_id=session_id,
        sequence_number=manager.get_next_sequence(session_id),
        event=welcome_event,
    )

    try:
        await websocket.send_text(envelope.model_dump_json())

        while True:
            data = await websocket.receive_text()

    except WebSocketDisconnect:
        manager.disconnect(session_id, websocket)
    except Exception:
        manager.disconnect(session_id, websocket)
