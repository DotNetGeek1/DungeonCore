from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from shared_config.settings import ServiceSettings
from shared_schemas import (
    CreateSessionRequest,
    CreateSessionResponse,
    GetEventHistoryResponse,
    GetSessionStateResponse,
    GetVisibleMessagesResponse,
    OperatorCommandRequest,
    OperatorCommandResponse,
)
from shared_schemas.enums import OperatorCommandType, SessionStatus

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import create_app
from app.routes.sessions import SESSION_STORE


@pytest.fixture
def settings() -> ServiceSettings:
    return ServiceSettings.for_service("api-gateway-test", 8000)


@pytest.fixture
def client(settings: ServiceSettings) -> TestClient:
    app = create_app(settings)
    SESSION_STORE.clear()
    return TestClient(app)


class TestHealthEndpoint:
    def test_health_returns_service_info(self, client: TestClient) -> None:
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "api-gateway-test"
        assert data["status"] in ("ok", "degraded")
        assert "dependencies" in data


class TestSessionEndpoints:
    def test_create_session(self, client: TestClient) -> None:
        request_data = {
            "campaign_id": "campaign-1",
            "scene_id": "scene-1",
            "player_character_ids": ["player-1", "player-2"],
            "npc_ids": ["npc-1"],
        }
        response = client.post("/sessions", json=request_data)
        assert response.status_code == 201
        data = response.json()

        assert "session" in data
        assert "state" in data
        assert data["session"]["campaign_id"] == "campaign-1"
        assert data["session"]["status"] == SessionStatus.RUNNING

    def test_get_session_state(self, client: TestClient) -> None:
        create_response = client.post(
            "/sessions",
            json={"campaign_id": "c1", "scene_id": "s1"},
        )
        session_id = create_response.json()["session"]["session_id"]

        response = client.get(f"/sessions/{session_id}/state")
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == session_id
        assert "state" in data

    def test_get_session_state_not_found(self, client: TestClient) -> None:
        response = client.get("/sessions/nonexistent/state")
        assert response.status_code == 404

    def test_get_event_history(self, client: TestClient) -> None:
        create_response = client.post(
            "/sessions",
            json={"campaign_id": "c1", "scene_id": "s1"},
        )
        session_id = create_response.json()["session"]["session_id"]

        response = client.get(f"/sessions/{session_id}/events")
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == session_id
        assert "events" in data

    def test_get_visible_messages(self, client: TestClient) -> None:
        create_response = client.post(
            "/sessions",
            json={"campaign_id": "c1", "scene_id": "s1"},
        )
        session_id = create_response.json()["session"]["session_id"]

        response = client.get(f"/sessions/{session_id}/messages")
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == session_id
        assert "messages" in data

    def test_pause_session(self, client: TestClient) -> None:
        create_response = client.post(
            "/sessions",
            json={"campaign_id": "c1", "scene_id": "s1"},
        )
        session_id = create_response.json()["session"]["session_id"]

        response = client.post(
            f"/sessions/{session_id}/pause",
            json={"command_type": "pause", "requested_by": "operator-1"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["accepted"] is True
        assert data["status"] == SessionStatus.PAUSED

    def test_pause_already_paused(self, client: TestClient) -> None:
        create_response = client.post(
            "/sessions",
            json={"campaign_id": "c1", "scene_id": "s1"},
        )
        session_id = create_response.json()["session"]["session_id"]

        client.post(
            f"/sessions/{session_id}/pause",
            json={"command_type": "pause", "requested_by": "operator-1"},
        )
        response = client.post(
            f"/sessions/{session_id}/pause",
            json={"command_type": "pause", "requested_by": "operator-1"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["accepted"] is False

    def test_resume_session(self, client: TestClient) -> None:
        create_response = client.post(
            "/sessions",
            json={"campaign_id": "c1", "scene_id": "s1"},
        )
        session_id = create_response.json()["session"]["session_id"]

        client.post(
            f"/sessions/{session_id}/pause",
            json={"command_type": "pause", "requested_by": "operator-1"},
        )

        response = client.post(
            f"/sessions/{session_id}/resume",
            json={"command_type": "resume", "requested_by": "operator-1"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["accepted"] is True
        assert data["status"] == SessionStatus.RUNNING

    def test_takeover_placeholder(self, client: TestClient) -> None:
        create_response = client.post(
            "/sessions",
            json={"campaign_id": "c1", "scene_id": "s1"},
        )
        session_id = create_response.json()["session"]["session_id"]

        response = client.post(
            f"/sessions/{session_id}/takeover",
            json={"command_type": "takeover", "requested_by": "human-1"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["accepted"] is True


class TestWebSocket:
    def test_websocket_connect(self, client: TestClient) -> None:
        with client.websocket_connect("/sessions/test-session/stream") as websocket:
            data = websocket.receive_json()
            assert data["session_id"] == "test-session"
            assert "event" in data
            assert data["event"]["event_type"] == "session.started"
