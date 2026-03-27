"""Integration tests for orchestrator - session lifecycle and state management."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from shared_config.settings import ServiceSettings
from shared_schemas.actions import AttackAction, DefendAction, PlayerTurn
from shared_schemas.enums import ActionType, ScenePhase
from shared_schemas.state import GameState

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import create_app
from app.service_integration import (
    StatePatch,
    apply_state_patches,
    get_fallback_turn,
)
from app.fixtures.mvp_scenario import create_mvp_game_state


class TestMVPSessionLifecycle:
    """Test starting and managing MVP scenarios."""

    @pytest.fixture
    def client(self, settings: ServiceSettings) -> TestClient:
        app = create_app(settings)
        with TestClient(app) as client:
            yield client

    def test_start_mvp_session(self, client: TestClient) -> None:
        """Starting MVP session should create a valid game state."""
        response = client.post("/sessions/start-mvp")
        assert response.status_code == 201

        data = response.json()
        assert "session_id" in data
        assert "state" in data
        assert data["phase"] == ScenePhase.SCENE_INTRO

        state = data["state"]
        assert "characters" in state
        assert "npcs" in state
        assert len(state["characters"]) == 2
        assert len(state["npcs"]) >= 2

    def test_get_mvp_session_state(self, client: TestClient) -> None:
        """Should be able to retrieve session state after creation."""
        create_response = client.post("/sessions/start-mvp")
        session_id = create_response.json()["session_id"]

        response = client.get(f"/sessions/{session_id}")
        assert response.status_code == 200

        data = response.json()
        assert data["session_id"] == session_id
        assert "state" in data

    def test_session_has_correct_initial_phase(self, client: TestClient) -> None:
        """New sessions should start in SCENE_INTRO phase."""
        response = client.post("/sessions/start-mvp")
        data = response.json()

        assert data["phase"] == ScenePhase.SCENE_INTRO

    def test_session_not_found_returns_404(self, client: TestClient) -> None:
        """Getting a non-existent session should return 404."""
        response = client.get("/sessions/nonexistent-id")
        assert response.status_code == 404


class TestMVPScenarioFixture:
    """Test the MVP scenario fixture creates correct state."""

    def test_mvp_state_has_characters(self) -> None:
        """MVP state should have player characters."""
        state = create_mvp_game_state("test-campaign", "test-session")
        assert len(state.characters) == 2
        char_names = [c.name for c in state.characters.values()]
        assert any("Theron" in name or "Fighter" in name for name in char_names)
        assert any("Lyra" in name or "Rogue" in name for name in char_names)

    def test_mvp_state_has_npcs(self) -> None:
        """MVP state should have NPCs."""
        state = create_mvp_game_state("test-campaign", "test-session")
        assert len(state.npcs) >= 2

    def test_mvp_state_has_objectives(self) -> None:
        """MVP state should have objectives."""
        state = create_mvp_game_state("test-campaign", "test-session")
        assert len(state.objectives) >= 1

    def test_mvp_state_has_scene(self) -> None:
        """MVP state should have a scene configured."""
        state = create_mvp_game_state("test-campaign", "test-session")
        assert state.scene is not None
        assert state.scene.name is not None
        assert state.scene.phase == ScenePhase.SCENE_INTRO


class TestFallbackBehavior:
    """Test fallback behavior patterns."""

    def test_get_fallback_turn_returns_defend(self) -> None:
        """Fallback turn should be a defend action."""
        fallback = get_fallback_turn()
        assert fallback.action is not None
        assert fallback.action.type == ActionType.DEFEND
        assert fallback.speech is not None

    def test_fallback_has_thought(self) -> None:
        """Fallback turn should have a thought explaining the fallback."""
        fallback = get_fallback_turn()
        assert fallback.thought is not None


class TestApplyStatePatchesFunction:
    """Test the apply_state_patches utility function."""

    def test_apply_hp_damage_to_character(self, mvp_state: GameState) -> None:
        """HP damage patch should correctly update character state."""
        char_id = list(mvp_state.characters.keys())[0]
        original_hp = mvp_state.characters[char_id].hp

        patches = [
            StatePatch(
                patch_type="damage",
                target_id=char_id,
                field="hp",
                old_value=original_hp,
                new_value=original_hp - 5,
            ),
        ]

        updated_state = apply_state_patches(mvp_state, patches)
        assert updated_state.characters[char_id].hp == original_hp - 5

    def test_apply_hp_damage_to_npc(self, mvp_state: GameState) -> None:
        """HP damage patch should correctly update NPC state."""
        npc_id = list(mvp_state.npcs.keys())[0]
        original_hp = mvp_state.npcs[npc_id].hp

        patches = [
            StatePatch(
                patch_type="damage",
                target_id=npc_id,
                field="hp",
                old_value=original_hp,
                new_value=0,
            ),
        ]

        updated_state = apply_state_patches(mvp_state, patches)
        assert updated_state.npcs[npc_id].hp == 0

    def test_apply_multiple_patches(self, mvp_state: GameState) -> None:
        """Multiple patches should all be applied."""
        char_id = list(mvp_state.characters.keys())[0]
        npc_id = list(mvp_state.npcs.keys())[0]

        patches = [
            StatePatch(
                patch_type="damage",
                target_id=char_id,
                field="hp",
                old_value=mvp_state.characters[char_id].hp,
                new_value=10,
            ),
            StatePatch(
                patch_type="damage",
                target_id=npc_id,
                field="hp",
                old_value=mvp_state.npcs[npc_id].hp,
                new_value=5,
            ),
        ]

        updated_state = apply_state_patches(mvp_state, patches)
        assert updated_state.characters[char_id].hp == 10
        assert updated_state.npcs[npc_id].hp == 5

    def test_patch_for_unknown_target_is_ignored(self, mvp_state: GameState) -> None:
        """Patches targeting unknown entities should be silently ignored."""
        patches = [
            StatePatch(
                patch_type="damage",
                target_id="nonexistent-entity",
                field="hp",
                old_value=10,
                new_value=5,
            ),
        ]

        updated_state = apply_state_patches(mvp_state, patches)
        assert updated_state.characters == dict(mvp_state.characters)

    def test_apply_alive_status_patch(self, mvp_state: GameState) -> None:
        """Alive status patch should update entity."""
        npc_id = list(mvp_state.npcs.keys())[0]

        patches = [
            StatePatch(
                patch_type="death",
                target_id=npc_id,
                field="alive",
                old_value=True,
                new_value=False,
            ),
        ]

        updated_state = apply_state_patches(mvp_state, patches)
        assert updated_state.npcs[npc_id].alive is False


class TestStateMachineIntegration:
    """Test state machine rules are enforced."""

    @pytest.fixture
    def client(self, settings: ServiceSettings) -> TestClient:
        app = create_app(settings)
        with TestClient(app) as client:
            yield client

    def test_session_starts_in_scene_intro(self, client: TestClient) -> None:
        """New sessions should start in SCENE_INTRO phase."""
        response = client.post("/sessions/start-mvp")
        data = response.json()

        assert data["phase"] == ScenePhase.SCENE_INTRO

    def test_health_endpoint(self, client: TestClient) -> None:
        """Health endpoint should return service info."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "service" in data
        assert "status" in data


class TestEventTypes:
    """Test event types used in orchestration."""

    def test_scene_phase_values(self) -> None:
        """ScenePhase enum should have expected values."""
        phases = [
            ScenePhase.SCENE_INTRO,
            ScenePhase.DISCUSSION,
            ScenePhase.ACTION_COMMIT,
            ScenePhase.RESOLUTION,
            ScenePhase.NARRATION,
            ScenePhase.REACTION,
            ScenePhase.TURN_END,
        ]
        assert len(phases) == 7

    def test_action_types_for_player(self) -> None:
        """ActionType enum should have expected player actions."""
        player_actions = [
            ActionType.ATTACK,
            ActionType.MOVE,
            ActionType.DEFEND,
            ActionType.INSPECT,
            ActionType.CAST_SPELL_BASIC,
        ]
        for action in player_actions:
            assert action.value is not None
