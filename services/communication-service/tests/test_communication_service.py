from __future__ import annotations

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from shared_config.settings import ServiceSettings
from shared_schemas.enums import (
    ActorRole,
    MessageChannel,
    ScenePhase,
    Visibility,
)
from shared_schemas.messages import TableMessage
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
from app.budgets import BudgetConfig, BudgetEnforcer
from app.visibility import VisibilityRules
from app.message_service import InMemoryMessageStore


TEST_TIMESTAMP = datetime(2026, 3, 24, 12, 0, 0)


@pytest.fixture
def settings() -> ServiceSettings:
    return ServiceSettings.for_service("communication-service-test", 8004)


@pytest.fixture
def client(settings: ServiceSettings) -> TestClient:
    app = create_app(settings)
    with TestClient(app) as client:
        yield client


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
            phase=ScenePhase.DISCUSSION,
        ),
        turn=TurnState(
            turn_number=1,
            round_number=1,
            active_actor_id="player-1",
            phase=ScenePhase.DISCUSSION,
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
            ),
            "player-2": CharacterState(
                actor_id="player-2",
                name="Mage",
                role=ActorRole.PLAYER,
                hp=15,
                max_hp=15,
                ac=12,
                visibility_scope=VisibilityScope(visibility=Visibility.PUBLIC),
            ),
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
        assert data["service"] == "communication-service-test"


class TestVisibilityRules:
    def test_in_character_public_visible_to_all(self, sample_state: GameState) -> None:
        rules = VisibilityRules()
        message = TableMessage(
            id="msg-1",
            session_id="session-1",
            scene_id="scene-1",
            turn_number=1,
            phase=ScenePhase.DISCUSSION,
            channel=MessageChannel.IN_CHARACTER,
            sender_id="player-1",
            recipient_ids=[],
            visibility=Visibility.PUBLIC,
            text="Hello, everyone!",
            created_at=TEST_TIMESTAMP,
        )

        result = rules.can_see_message(message, "player-2", sample_state)
        assert result.visible is True

    def test_table_talk_visible_to_players(self, sample_state: GameState) -> None:
        rules = VisibilityRules()
        message = TableMessage(
            id="msg-1",
            session_id="session-1",
            scene_id="scene-1",
            turn_number=1,
            phase=ScenePhase.DISCUSSION,
            channel=MessageChannel.TABLE_TALK,
            sender_id="player-1",
            recipient_ids=[],
            visibility=Visibility.PARTY,
            text="Focus the goblin!",
            created_at=TEST_TIMESTAMP,
        )

        player_result = rules.can_see_message(message, "player-2", sample_state)
        assert player_result.visible is True

        npc_result = rules.can_see_message(message, "goblin-1", sample_state)
        assert npc_result.visible is False

    def test_private_whisper_only_to_recipients(self, sample_state: GameState) -> None:
        rules = VisibilityRules()
        message = TableMessage(
            id="msg-1",
            session_id="session-1",
            scene_id="scene-1",
            turn_number=1,
            phase=ScenePhase.DISCUSSION,
            channel=MessageChannel.PRIVATE_WHISPER,
            sender_id="player-1",
            recipient_ids=["player-2"],
            visibility=Visibility.PRIVATE,
            text="I have a secret plan...",
            created_at=TEST_TIMESTAMP,
        )

        recipient_result = rules.can_see_message(message, "player-2", sample_state)
        assert recipient_result.visible is True

        other_result = rules.can_see_message(message, "goblin-1", sample_state)
        assert other_result.visible is False

    def test_dm_notice_only_to_recipients(self, sample_state: GameState) -> None:
        rules = VisibilityRules()
        message = TableMessage(
            id="msg-1",
            session_id="session-1",
            scene_id="scene-1",
            turn_number=1,
            phase=ScenePhase.DISCUSSION,
            channel=MessageChannel.DM_NOTICE,
            sender_id="dm-1",
            recipient_ids=["player-1"],
            visibility=Visibility.PRIVATE,
            text="You notice a trap...",
            created_at=TEST_TIMESTAMP,
        )

        recipient_result = rules.can_see_message(message, "player-1", sample_state)
        assert recipient_result.visible is True

        other_result = rules.can_see_message(message, "player-2", sample_state)
        assert other_result.visible is False


class TestVisibilityRulesEdgeCases:
    """Edge case tests for message visibility rules."""

    def test_sender_can_always_see_own_message(self, sample_state: GameState) -> None:
        """Sender should always see their own message regardless of visibility settings."""
        rules = VisibilityRules()
        message = TableMessage(
            id="msg-1",
            session_id="session-1",
            scene_id="scene-1",
            turn_number=1,
            phase=ScenePhase.DISCUSSION,
            channel=MessageChannel.PRIVATE_WHISPER,
            sender_id="player-1",
            recipient_ids=["player-2"],
            visibility=Visibility.PRIVATE,
            text="Secret message",
            created_at=TEST_TIMESTAMP,
        )

        result = rules.can_see_message(message, "player-1", sample_state)
        assert result.visible is True
        assert "sender" in result.reason.lower()

    def test_dm_notice_to_multiple_recipients(self, sample_state: GameState) -> None:
        """DM notice with multiple recipients should be visible to all of them."""
        rules = VisibilityRules()
        message = TableMessage(
            id="msg-1",
            session_id="session-1",
            scene_id="scene-1",
            turn_number=1,
            phase=ScenePhase.DISCUSSION,
            channel=MessageChannel.DM_NOTICE,
            sender_id="dm-1",
            recipient_ids=["player-1", "player-2"],
            visibility=Visibility.PRIVATE,
            text="You both notice something strange...",
            created_at=TEST_TIMESTAMP,
        )

        result1 = rules.can_see_message(message, "player-1", sample_state)
        result2 = rules.can_see_message(message, "player-2", sample_state)
        result_npc = rules.can_see_message(message, "goblin-1", sample_state)

        assert result1.visible is True
        assert result2.visible is True
        assert result_npc.visible is False

    def test_in_character_visible_to_npcs_in_scene(self, sample_state: GameState) -> None:
        """NPCs in the scene should see public in-character messages."""
        rules = VisibilityRules()
        message = TableMessage(
            id="msg-1",
            session_id="session-1",
            scene_id="scene-1",
            turn_number=1,
            phase=ScenePhase.DISCUSSION,
            channel=MessageChannel.IN_CHARACTER,
            sender_id="player-1",
            recipient_ids=[],
            visibility=Visibility.PUBLIC,
            text="I challenge you, goblin!",
            created_at=TEST_TIMESTAMP,
        )

        result = rules.can_see_message(message, "goblin-1", sample_state)
        assert result.visible is True

    def test_table_talk_with_explicit_npc_recipient(self, sample_state: GameState) -> None:
        """NPC explicitly added to recipients should see table talk."""
        rules = VisibilityRules()
        message = TableMessage(
            id="msg-1",
            session_id="session-1",
            scene_id="scene-1",
            turn_number=1,
            phase=ScenePhase.DISCUSSION,
            channel=MessageChannel.TABLE_TALK,
            sender_id="player-1",
            recipient_ids=["goblin-1"],
            visibility=Visibility.PARTY,
            text="Psst, goblin, want to make a deal?",
            created_at=TEST_TIMESTAMP,
        )

        result = rules.can_see_message(message, "goblin-1", sample_state)
        assert result.visible is True

    def test_private_whisper_not_visible_to_non_recipients(self, sample_state: GameState) -> None:
        """Private whisper should not be visible to anyone not in recipient list."""
        rules = VisibilityRules()
        message = TableMessage(
            id="msg-1",
            session_id="session-1",
            scene_id="scene-1",
            turn_number=1,
            phase=ScenePhase.DISCUSSION,
            channel=MessageChannel.PRIVATE_WHISPER,
            sender_id="player-1",
            recipient_ids=["player-2"],
            visibility=Visibility.PRIVATE,
            text="Secret plan...",
            created_at=TEST_TIMESTAMP,
        )

        result_other_player = rules.can_see_message(message, "player-3", sample_state)
        result_npc = rules.can_see_message(message, "goblin-1", sample_state)

        assert result_other_player.visible is False
        assert result_npc.visible is False

    def test_filter_visible_messages(self, sample_state: GameState) -> None:
        """Test filtering a list of messages by visibility."""
        rules = VisibilityRules()

        public_msg = TableMessage(
            id="msg-1",
            session_id="session-1",
            scene_id="scene-1",
            turn_number=1,
            phase=ScenePhase.DISCUSSION,
            channel=MessageChannel.IN_CHARACTER,
            sender_id="player-1",
            recipient_ids=[],
            visibility=Visibility.PUBLIC,
            text="Hello everyone!",
            created_at=TEST_TIMESTAMP,
        )

        private_msg = TableMessage(
            id="msg-2",
            session_id="session-1",
            scene_id="scene-1",
            turn_number=1,
            phase=ScenePhase.DISCUSSION,
            channel=MessageChannel.PRIVATE_WHISPER,
            sender_id="player-1",
            recipient_ids=["player-2"],
            visibility=Visibility.PRIVATE,
            text="Secret!",
            created_at=TEST_TIMESTAMP,
        )

        dm_notice = TableMessage(
            id="msg-3",
            session_id="session-1",
            scene_id="scene-1",
            turn_number=1,
            phase=ScenePhase.DISCUSSION,
            channel=MessageChannel.DM_NOTICE,
            sender_id="dm-1",
            recipient_ids=["player-1"],
            visibility=Visibility.PRIVATE,
            text="You notice a trap",
            created_at=TEST_TIMESTAMP,
        )

        all_messages = [public_msg, private_msg, dm_notice]

        player1_visible = rules.filter_visible_messages(all_messages, "player-1", sample_state)
        assert len(player1_visible) == 3

        player2_visible = rules.filter_visible_messages(all_messages, "player-2", sample_state)
        assert len(player2_visible) == 2
        assert private_msg in player2_visible
        assert dm_notice not in player2_visible

        goblin_visible = rules.filter_visible_messages(all_messages, "goblin-1", sample_state)
        assert len(goblin_visible) == 1
        assert public_msg in goblin_visible

    def test_visibility_with_empty_recipient_list(self, sample_state: GameState) -> None:
        """Messages with empty recipient list should follow channel rules."""
        rules = VisibilityRules()

        message = TableMessage(
            id="msg-1",
            session_id="session-1",
            scene_id="scene-1",
            turn_number=1,
            phase=ScenePhase.DISCUSSION,
            channel=MessageChannel.TABLE_TALK,
            sender_id="player-1",
            recipient_ids=[],
            visibility=Visibility.PUBLIC,
            text="General announcement",
            created_at=TEST_TIMESTAMP,
        )

        player_result = rules.can_see_message(message, "player-2", sample_state)
        assert player_result.visible is True

    def test_dm_only_visibility(self, sample_state: GameState) -> None:
        """DM_ONLY visibility should only be visible to DM and sender."""
        rules = VisibilityRules()

        message = TableMessage(
            id="msg-1",
            session_id="session-1",
            scene_id="scene-1",
            turn_number=1,
            phase=ScenePhase.DISCUSSION,
            channel=MessageChannel.DM_NOTICE,
            sender_id="dm-1",
            recipient_ids=["dm-1"],
            visibility=Visibility.DM_ONLY,
            text="DM notes",
            created_at=TEST_TIMESTAMP,
        )

        player_result = rules.can_see_message(message, "player-1", sample_state)
        assert player_result.visible is False

        dm_result = rules.can_see_message(message, "dm-1", sample_state)
        assert dm_result.visible is True


class TestBudgetEnforcer:
    def test_message_within_budget(self) -> None:
        enforcer = BudgetEnforcer()
        result = enforcer.check_message_budget(
            sender_id="player-1",
            channel=MessageChannel.TABLE_TALK,
            text="Hello",
            existing_messages=[],
        )
        assert result.allowed is True

    def test_message_exceeds_length(self) -> None:
        enforcer = BudgetEnforcer(BudgetConfig(max_message_length=10))
        result = enforcer.check_message_budget(
            sender_id="player-1",
            channel=MessageChannel.TABLE_TALK,
            text="This is a very long message that exceeds the limit",
            existing_messages=[],
        )
        assert result.allowed is False
        assert "length" in result.reason.lower()

    def test_actor_budget_exceeded(self, sample_state: GameState) -> None:
        enforcer = BudgetEnforcer(BudgetConfig(max_messages_per_actor_per_discussion=1))

        existing = [
            TableMessage(
                id="msg-1",
                session_id="session-1",
                scene_id="scene-1",
                turn_number=1,
                phase=ScenePhase.DISCUSSION,
                channel=MessageChannel.TABLE_TALK,
                sender_id="player-1",
                recipient_ids=[],
                visibility=Visibility.PARTY,
                text="First message",
                created_at=TEST_TIMESTAMP,
            )
        ]

        result = enforcer.check_message_budget(
            sender_id="player-1",
            channel=MessageChannel.TABLE_TALK,
            text="Second message",
            existing_messages=existing,
        )
        assert result.allowed is False


class TestMessageEndpoints:
    def test_create_message(self, client: TestClient) -> None:
        response = client.post(
            "/messages",
            json={
                "session_id": "session-1",
                "scene_id": "scene-1",
                "turn_number": 1,
                "phase": "discussion",
                "channel": "table_talk",
                "sender_id": "player-1",
                "text": "Let's focus the goblin!",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["success"] is True
        assert data["message"]["text"] == "Let's focus the goblin!"

    def test_get_messages(self, client: TestClient) -> None:
        client.post(
            "/messages",
            json={
                "session_id": "session-1",
                "scene_id": "scene-1",
                "turn_number": 1,
                "phase": "discussion",
                "channel": "in_character",
                "sender_id": "player-1",
                "text": "Hello!",
            },
        )

        response = client.get("/sessions/session-1/messages")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        assert len(data["messages"]) >= 1

    def test_get_budget(self, client: TestClient) -> None:
        response = client.get(
            "/sessions/session-1/budget",
            params={
                "turn_number": 1,
                "sender_id": "player-1",
                "channel": "table_talk",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "total_remaining" in data
        assert "actor_remaining" in data
        assert "channel_remaining" in data

    def test_register_session(self, client: TestClient, sample_state: GameState) -> None:
        response = client.post(
            "/sessions/session-1/register",
            json={"state": sample_state.model_dump(mode="json")},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["registered"] is True
