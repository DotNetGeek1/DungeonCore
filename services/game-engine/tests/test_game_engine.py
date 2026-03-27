from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from shared_config.settings import ServiceSettings
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

from app.main import create_app
from app.dice import DiceRoller, DiceRoll


@pytest.fixture
def settings() -> ServiceSettings:
    return ServiceSettings.for_service("game-engine-test", 8003)


@pytest.fixture
def client(settings: ServiceSettings) -> TestClient:
    app = create_app(settings)
    return TestClient(app)


@pytest.fixture
def sample_state() -> GameState:
    return GameState(
        campaign_id="campaign-1",
        session_id="session-1",
        scene=SceneState(
            scene_id="scene-1",
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
                name="Hero",
                role=ActorRole.PLAYER,
                hp=20,
                max_hp=20,
                ac=15,
                visibility_scope=VisibilityScope(visibility=Visibility.PUBLIC),
            )
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
            )
        },
        objectives=[],
        flags={},
    )


class TestHealthEndpoint:
    def test_health_returns_service_info(self, client: TestClient) -> None:
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "game-engine-test"
        assert data["status"] in ("ok", "degraded")


class TestDiceRoller:
    def test_seeded_roller_is_deterministic(self) -> None:
        roller1 = DiceRoller(seed=42)
        roller2 = DiceRoller(seed=42)

        rolls1 = [roller1.roll_d20().value for _ in range(5)]
        rolls2 = [roller2.roll_d20().value for _ in range(5)]

        assert rolls1 == rolls2

    def test_roll_d20_in_range(self) -> None:
        roller = DiceRoller()
        for _ in range(100):
            roll = roller.roll_d20()
            assert 1 <= roll.value <= 20

    def test_roll_with_modifier(self) -> None:
        roller = DiceRoller(seed=42)
        roll = roller.roll_d20(modifier=5)
        assert roll.modifier == 5
        assert roll.total == roll.value + 5

    def test_roll_damage(self) -> None:
        roller = DiceRoller(seed=42)
        rolls = roller.roll_damage("d6", count=3, modifier=2)
        assert len(rolls) == 3
        assert rolls[-1].modifier == 2


class TestValidation:
    def test_validate_attack_valid(self, client: TestClient, sample_state: GameState) -> None:
        response = client.post(
            "/validate",
            json={
                "action": {"type": "attack", "target_id": "goblin-1"},
                "actor_id": "player-1",
                "state": sample_state.model_dump(mode="json"),
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True

    def test_validate_attack_target_not_found(self, client: TestClient, sample_state: GameState) -> None:
        response = client.post(
            "/validate",
            json={
                "action": {"type": "attack", "target_id": "nonexistent"},
                "actor_id": "player-1",
                "state": sample_state.model_dump(mode="json"),
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert any("does not exist" in e for e in data["errors"])

    def test_validate_move_valid(self, client: TestClient, sample_state: GameState) -> None:
        response = client.post(
            "/validate",
            json={
                "action": {"type": "move", "movement_path": ["A1", "A2", "A3"]},
                "actor_id": "player-1",
                "state": sample_state.model_dump(mode="json"),
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True

    def test_validate_move_exceeds_budget(self, client: TestClient, sample_state: GameState) -> None:
        response = client.post(
            "/validate",
            json={
                "action": {"type": "move", "movement_path": ["A1", "A2", "A3", "A4", "A5", "A6", "A7"]},
                "actor_id": "player-1",
                "state": sample_state.model_dump(mode="json"),
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False
        assert any("exceeds maximum" in e for e in data["errors"])

    def test_validate_defend_valid(self, client: TestClient, sample_state: GameState) -> None:
        response = client.post(
            "/validate",
            json={
                "action": {"type": "defend", "stance": "guard"},
                "actor_id": "player-1",
                "state": sample_state.model_dump(mode="json"),
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True

    def test_validate_inspect_valid(self, client: TestClient, sample_state: GameState) -> None:
        response = client.post(
            "/validate",
            json={
                "action": {"type": "inspect", "target_id": "goblin-1"},
                "actor_id": "player-1",
                "state": sample_state.model_dump(mode="json"),
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True


class TestResolution:
    def test_resolve_attack_deterministic(self, client: TestClient, sample_state: GameState) -> None:
        response = client.post(
            "/resolve",
            json={
                "action": {"type": "attack", "target_id": "goblin-1"},
                "actor_id": "player-1",
                "state": sample_state.model_dump(mode="json"),
                "seed": 42,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["action_type"] == "attack"
        assert "hit" in data
        assert len(data["dice_rolls"]) >= 1

    def test_resolve_move(self, client: TestClient, sample_state: GameState) -> None:
        response = client.post(
            "/resolve",
            json={
                "action": {"type": "move", "movement_path": ["A1", "A2"]},
                "actor_id": "player-1",
                "state": sample_state.model_dump(mode="json"),
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["action_type"] == "move"
        assert len(data["state_patches"]) >= 1


class TestDiceEndpoint:
    def test_roll_dice(self, client: TestClient) -> None:
        response = client.post(
            "/roll",
            json={"die": "d20", "modifier": 5, "count": 1},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["rolls"]) == 1
        assert data["rolls"][0]["modifier"] == 5

    def test_roll_dice_seeded(self, client: TestClient) -> None:
        response1 = client.post("/roll", json={"die": "d20", "seed": 42})
        response2 = client.post("/roll", json={"die": "d20", "seed": 42})

        assert response1.json()["rolls"][0]["value"] == response2.json()["rolls"][0]["value"]

    def test_roll_multiple_dice(self, client: TestClient) -> None:
        response = client.post(
            "/roll",
            json={"die": "d6", "count": 3, "modifier": 2},
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["rolls"]) == 3
