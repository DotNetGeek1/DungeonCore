from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from shared_config.settings import ServiceSettings
from shared_schemas.enums import ScenePhase

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import create_app
from app.state_machine import (
    StateMachine,
    PhaseContext,
    TransitionError,
    ALLOWED_TRANSITIONS,
    create_phase_context,
)


@pytest.fixture
def settings() -> ServiceSettings:
    return ServiceSettings.for_service("orchestrator-test", 8001)


@pytest.fixture
def client(settings: ServiceSettings) -> TestClient:
    app = create_app(settings)
    app.state.sessions = {}
    return TestClient(app)


class TestHealthEndpoint:
    def test_health_returns_service_info(self, client: TestClient) -> None:
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "orchestrator-test"
        assert data["status"] in ("ok", "degraded")


class TestStateMachine:
    def test_allowed_transitions_from_scene_intro(self) -> None:
        sm = StateMachine()
        assert sm.can_transition(ScenePhase.SCENE_INTRO, ScenePhase.DISCUSSION)
        assert not sm.can_transition(ScenePhase.SCENE_INTRO, ScenePhase.RESOLUTION)

    def test_allowed_transitions_full_cycle(self) -> None:
        sm = StateMachine()
        assert sm.can_transition(ScenePhase.SCENE_INTRO, ScenePhase.DISCUSSION)
        assert sm.can_transition(ScenePhase.DISCUSSION, ScenePhase.ACTION_COMMIT)
        assert sm.can_transition(ScenePhase.ACTION_COMMIT, ScenePhase.RESOLUTION)
        assert sm.can_transition(ScenePhase.RESOLUTION, ScenePhase.NARRATION)
        assert sm.can_transition(ScenePhase.NARRATION, ScenePhase.REACTION)
        assert sm.can_transition(ScenePhase.REACTION, ScenePhase.TURN_END)
        assert sm.can_transition(ScenePhase.TURN_END, ScenePhase.DISCUSSION)

    def test_invalid_transition_raises_error(self) -> None:
        sm = StateMachine()
        with pytest.raises(TransitionError):
            sm.validate_transition(ScenePhase.SCENE_INTRO, ScenePhase.TURN_END)

    def test_next_phase(self) -> None:
        sm = StateMachine()
        assert sm.next_phase(ScenePhase.SCENE_INTRO) == ScenePhase.DISCUSSION
        assert sm.next_phase(ScenePhase.DISCUSSION) == ScenePhase.ACTION_COMMIT


class TestSessionEndpoints:
    def test_start_session(self, client: TestClient) -> None:
        response = client.post(
            "/sessions/start",
            json={
                "campaign_id": "campaign-1",
                "scene_id": "scene-1",
                "player_ids": ["player-1", "player-2"],
                "npc_ids": ["npc-1"],
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert "session_id" in data
        assert "state" in data
        assert data["phase"] == ScenePhase.SCENE_INTRO

    def test_get_session(self, client: TestClient) -> None:
        create_response = client.post(
            "/sessions/start",
            json={"campaign_id": "c1", "scene_id": "s1"},
        )
        session_id = create_response.json()["session_id"]

        response = client.get(f"/sessions/{session_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == session_id

    def test_get_session_not_found(self, client: TestClient) -> None:
        response = client.get("/sessions/nonexistent")
        assert response.status_code == 404

    def test_run_turn_advances_phase(self, client: TestClient) -> None:
        create_response = client.post(
            "/sessions/start",
            json={"campaign_id": "c1", "scene_id": "s1"},
        )
        session_id = create_response.json()["session_id"]
        initial_phase = create_response.json()["phase"]
        assert initial_phase == ScenePhase.SCENE_INTRO

        response = client.post(
            f"/sessions/{session_id}/turn",
            json={"force": False},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["phase"] == ScenePhase.DISCUSSION

    def test_advance_phase(self, client: TestClient) -> None:
        create_response = client.post(
            "/sessions/start",
            json={"campaign_id": "c1", "scene_id": "s1"},
        )
        session_id = create_response.json()["session_id"]

        response = client.post(f"/sessions/{session_id}/advance-phase")
        assert response.status_code == 200
        data = response.json()
        assert data["phase"] == ScenePhase.DISCUSSION


class TestTurnRunner:
    def test_turn_runner_handles_scene_intro(self, client: TestClient) -> None:
        create_response = client.post(
            "/sessions/start",
            json={"campaign_id": "c1", "scene_id": "s1"},
        )
        session_id = create_response.json()["session_id"]

        response = client.post(
            f"/sessions/{session_id}/turn",
            json={"force": False},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["events_count"] >= 0
