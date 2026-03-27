from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from shared_config.settings import ServiceSettings
from shared_schemas.enums import (
    ActionType,
    ActorRole,
    MemoryType,
    ScenePhase,
    Visibility,
)
from shared_schemas.memory import MemoryEntry
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
from app.context_builder import ContextBuilder
from app.memory_retrieval import InMemoryMemoryStore, MemoryRetriever
from app.validation import OutputValidator


@pytest.fixture
def settings() -> ServiceSettings:
    return ServiceSettings.for_service("agent-runtime-test", 8002)


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
            summary="A test scene for validation",
            turn_number=5,
            active_actor_id="player-1",
            phase=ScenePhase.ACTION_COMMIT,
        ),
        turn=TurnState(
            turn_number=5,
            round_number=2,
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
        assert data["service"] == "agent-runtime-test"
        assert "model_provider" in data


class TestOutputValidator:
    def test_valid_player_turn(self) -> None:
        validator = OutputValidator()
        raw = json.dumps({
            "speech": "I attack the goblin!",
            "action": {"type": "attack", "target_id": "goblin-1"},
        })

        result = validator.validate_player_turn(raw)
        assert result.valid is True
        assert result.parsed is not None
        assert result.parsed.speech == "I attack the goblin!"

    def test_valid_turn_with_markdown(self) -> None:
        validator = OutputValidator()
        raw = """```json
{
  "speech": "Hello!",
  "table_talk": "Focus the enemy"
}
```"""

        result = validator.validate_player_turn(raw)
        assert result.valid is True
        assert result.parsed is not None

    def test_invalid_json(self) -> None:
        validator = OutputValidator()
        raw = "this is not json"

        result = validator.validate_player_turn(raw)
        assert result.valid is False
        assert len(result.errors) > 0

    def test_missing_required_output(self) -> None:
        validator = OutputValidator()
        raw = json.dumps({"thought": "Just thinking..."})

        result = validator.validate_player_turn(raw)
        assert result.valid is False


class TestContextBuilder:
    def test_build_context(self, sample_state: GameState) -> None:
        builder = ContextBuilder()

        ctx = builder.build_context(
            session_id="session-1",
            agent_id="agent-1",
            actor_id="player-1",
            actor_name="Hero",
            role=ActorRole.PLAYER,
            goals=["Defeat the goblins", "Find the treasure"],
            state=sample_state,
        )

        assert ctx.session_id == "session-1"
        assert ctx.identity.agent_id == "agent-1"
        assert ctx.identity.actor_id == "player-1"
        assert ctx.identity.name == "Hero"
        assert len(ctx.identity.goals) == 2
        assert len(ctx.allowed_actions) > 0

    def test_filters_visible_state(self, sample_state: GameState) -> None:
        builder = ContextBuilder()

        ctx = builder.build_context(
            session_id="session-1",
            agent_id="agent-1",
            actor_id="player-1",
            actor_name="Hero",
            role=ActorRole.PLAYER,
            goals=[],
            state=sample_state,
        )

        assert "player-1" in ctx.visible_state.characters
        assert "goblin-1" in ctx.visible_state.npcs


class TestMemoryRetriever:
    def test_retrieve_empty(self) -> None:
        store = InMemoryMemoryStore()
        retriever = MemoryRetriever(store=store)

        memories = retriever.retrieve(
            session_id="session-1",
            actor_id="player-1",
            current_turn=5,
        )

        assert memories == []

    def test_retrieve_by_importance(self) -> None:
        store = InMemoryMemoryStore()

        high_importance = MemoryEntry(
            id="mem-1",
            session_id="session-1",
            actor_id="player-1",
            memory_type=MemoryType.OBSERVATION,
            text="The goblin has a weakness to fire",
            importance=9,
            tags=["combat"],
            created_at_turn=3,
            visibility=Visibility.PRIVATE,
        )
        low_importance = MemoryEntry(
            id="mem-2",
            session_id="session-1",
            actor_id="player-1",
            memory_type=MemoryType.OBSERVATION,
            text="The floor is dirty",
            importance=2,
            tags=[],
            created_at_turn=4,
            visibility=Visibility.PRIVATE,
        )

        store.save(low_importance)
        store.save(high_importance)

        retriever = MemoryRetriever(store=store)
        memories = retriever.retrieve(
            session_id="session-1",
            actor_id="player-1",
            current_turn=5,
        )

        assert len(memories) == 2
        assert memories[0].id == "mem-1"


class TestMemoryRetrieverEdgeCases:
    """Edge case tests for memory retrieval."""

    def test_filter_by_tag(self) -> None:
        """Memory retrieval should filter by tags when specified."""
        store = InMemoryMemoryStore()

        combat_memory = MemoryEntry(
            id="mem-1",
            session_id="session-1",
            actor_id="player-1",
            memory_type=MemoryType.OBSERVATION,
            text="The goblin has a weakness to fire",
            importance=8,
            tags=["combat", "goblin"],
            created_at_turn=3,
            visibility=Visibility.PRIVATE,
        )
        exploration_memory = MemoryEntry(
            id="mem-2",
            session_id="session-1",
            actor_id="player-1",
            memory_type=MemoryType.OBSERVATION,
            text="Found a secret passage",
            importance=7,
            tags=["exploration", "secret"],
            created_at_turn=4,
            visibility=Visibility.PRIVATE,
        )

        store.save(combat_memory)
        store.save(exploration_memory)

        retriever = MemoryRetriever(store=store)

        combat_memories = retriever.retrieve(
            session_id="session-1",
            actor_id="player-1",
            current_turn=5,
            tags=["combat"],
        )
        assert len(combat_memories) == 1
        assert combat_memories[0].id == "mem-1"

        exploration_memories = retriever.retrieve(
            session_id="session-1",
            actor_id="player-1",
            current_turn=5,
            tags=["exploration"],
        )
        assert len(exploration_memories) == 1
        assert exploration_memories[0].id == "mem-2"

    def test_filter_by_memory_type(self) -> None:
        """Memory retrieval should filter by memory type when specified."""
        store = InMemoryMemoryStore()

        observation = MemoryEntry(
            id="mem-obs",
            session_id="session-1",
            actor_id="player-1",
            memory_type=MemoryType.OBSERVATION,
            text="The goblin looks scared",
            importance=6,
            tags=[],
            created_at_turn=3,
            visibility=Visibility.PRIVATE,
        )
        summary = MemoryEntry(
            id="mem-summary",
            session_id="session-1",
            actor_id="player-1",
            memory_type=MemoryType.SUMMARY,
            text="Session started in the dungeon",
            importance=5,
            tags=[],
            created_at_turn=1,
            visibility=Visibility.PRIVATE,
        )
        belief = MemoryEntry(
            id="mem-belief",
            session_id="session-1",
            actor_id="player-1",
            memory_type=MemoryType.BELIEF,
            text="The NPC seems trustworthy",
            importance=7,
            tags=[],
            created_at_turn=2,
            visibility=Visibility.PRIVATE,
        )

        store.save(observation)
        store.save(summary)
        store.save(belief)

        retriever = MemoryRetriever(store=store)

        observations = retriever.retrieve(
            session_id="session-1",
            actor_id="player-1",
            current_turn=5,
            memory_types=[MemoryType.OBSERVATION],
        )
        assert len(observations) == 1
        assert observations[0].memory_type == MemoryType.OBSERVATION

        belief_and_summary = retriever.retrieve(
            session_id="session-1",
            actor_id="player-1",
            current_turn=5,
            memory_types=[MemoryType.BELIEF, MemoryType.SUMMARY],
        )
        assert len(belief_and_summary) == 2

    def test_retrieve_by_type_helper(self) -> None:
        """Test the retrieve_by_type convenience method."""
        store = InMemoryMemoryStore()

        observation = MemoryEntry(
            id="mem-1",
            session_id="session-1",
            actor_id="player-1",
            memory_type=MemoryType.OBSERVATION,
            text="Saw a trap",
            importance=6,
            tags=[],
            created_at_turn=3,
            visibility=Visibility.PRIVATE,
        )
        summary = MemoryEntry(
            id="mem-2",
            session_id="session-1",
            actor_id="player-1",
            memory_type=MemoryType.SUMMARY,
            text="Turn summary",
            importance=5,
            tags=[],
            created_at_turn=4,
            visibility=Visibility.PRIVATE,
        )

        store.save(observation)
        store.save(summary)

        retriever = MemoryRetriever(store=store)

        result = retriever.retrieve_by_type(
            session_id="session-1",
            actor_id="player-1",
            memory_type=MemoryType.OBSERVATION,
            current_turn=5,
        )
        assert len(result) == 1
        assert result[0].memory_type == MemoryType.OBSERVATION

    def test_recency_scoring(self) -> None:
        """More recent memories should score higher with recency weight."""
        from app.memory_retrieval import RetrievalConfig

        store = InMemoryMemoryStore()

        old_memory = MemoryEntry(
            id="mem-old",
            session_id="session-1",
            actor_id="player-1",
            memory_type=MemoryType.OBSERVATION,
            text="Old observation",
            importance=5,
            tags=[],
            created_at_turn=1,
            visibility=Visibility.PRIVATE,
        )
        recent_memory = MemoryEntry(
            id="mem-recent",
            session_id="session-1",
            actor_id="player-1",
            memory_type=MemoryType.OBSERVATION,
            text="Recent observation",
            importance=5,
            tags=[],
            created_at_turn=9,
            visibility=Visibility.PRIVATE,
        )

        store.save(old_memory)
        store.save(recent_memory)

        retriever = MemoryRetriever(
            store=store,
            config=RetrievalConfig(recency_weight=0.9, importance_weight=0.1),
        )

        memories = retriever.retrieve(
            session_id="session-1",
            actor_id="player-1",
            current_turn=10,
        )
        assert len(memories) == 2
        assert memories[0].id == "mem-recent"

    def test_importance_threshold(self) -> None:
        """Memories below min_importance should be filtered out."""
        from app.memory_retrieval import RetrievalConfig

        store = InMemoryMemoryStore()

        low_importance = MemoryEntry(
            id="mem-low",
            session_id="session-1",
            actor_id="player-1",
            memory_type=MemoryType.OBSERVATION,
            text="Trivial observation",
            importance=2,
            tags=[],
            created_at_turn=3,
            visibility=Visibility.PRIVATE,
        )
        high_importance = MemoryEntry(
            id="mem-high",
            session_id="session-1",
            actor_id="player-1",
            memory_type=MemoryType.OBSERVATION,
            text="Critical observation",
            importance=8,
            tags=[],
            created_at_turn=4,
            visibility=Visibility.PRIVATE,
        )

        store.save(low_importance)
        store.save(high_importance)

        retriever = MemoryRetriever(
            store=store,
            config=RetrievalConfig(min_importance=5),
        )

        memories = retriever.retrieve(
            session_id="session-1",
            actor_id="player-1",
            current_turn=5,
        )
        assert len(memories) == 1
        assert memories[0].id == "mem-high"

    def test_max_results_limit(self) -> None:
        """Should respect max_results configuration."""
        from app.memory_retrieval import RetrievalConfig

        store = InMemoryMemoryStore()

        for i in range(10):
            memory = MemoryEntry(
                id=f"mem-{i}",
                session_id="session-1",
                actor_id="player-1",
                memory_type=MemoryType.OBSERVATION,
                text=f"Observation {i}",
                importance=5,
                tags=[],
                created_at_turn=i,
                visibility=Visibility.PRIVATE,
            )
            store.save(memory)

        retriever = MemoryRetriever(
            store=store,
            config=RetrievalConfig(max_results=3),
        )

        memories = retriever.retrieve(
            session_id="session-1",
            actor_id="player-1",
            current_turn=10,
        )
        assert len(memories) == 3

    def test_retrieve_recent_with_lookback(self) -> None:
        """Test retrieve_recent respects lookback_turns parameter."""
        store = InMemoryMemoryStore()

        for i in range(10):
            memory = MemoryEntry(
                id=f"mem-{i}",
                session_id="session-1",
                actor_id="player-1",
                memory_type=MemoryType.OBSERVATION,
                text=f"Turn {i} observation",
                importance=5,
                tags=[],
                created_at_turn=i,
                visibility=Visibility.PRIVATE,
            )
            store.save(memory)

        retriever = MemoryRetriever(store=store)

        recent = retriever.retrieve_recent(
            session_id="session-1",
            actor_id="player-1",
            current_turn=10,
            lookback_turns=3,
        )

        for m in recent:
            assert m.created_at_turn >= 7

    def test_multiple_tags_any_match(self) -> None:
        """Memory should be returned if ANY specified tag matches."""
        store = InMemoryMemoryStore()

        memory = MemoryEntry(
            id="mem-1",
            session_id="session-1",
            actor_id="player-1",
            memory_type=MemoryType.OBSERVATION,
            text="Combat observation",
            importance=6,
            tags=["combat"],
            created_at_turn=3,
            visibility=Visibility.PRIVATE,
        )
        store.save(memory)

        retriever = MemoryRetriever(store=store)

        result = retriever.retrieve(
            session_id="session-1",
            actor_id="player-1",
            current_turn=5,
            tags=["exploration", "combat", "puzzle"],
        )
        assert len(result) == 1

    def test_isolation_between_actors(self) -> None:
        """Memories should be isolated per actor."""
        store = InMemoryMemoryStore()

        player1_memory = MemoryEntry(
            id="mem-p1",
            session_id="session-1",
            actor_id="player-1",
            memory_type=MemoryType.OBSERVATION,
            text="Player 1 observation",
            importance=5,
            tags=[],
            created_at_turn=3,
            visibility=Visibility.PRIVATE,
        )
        player2_memory = MemoryEntry(
            id="mem-p2",
            session_id="session-1",
            actor_id="player-2",
            memory_type=MemoryType.OBSERVATION,
            text="Player 2 observation",
            importance=5,
            tags=[],
            created_at_turn=3,
            visibility=Visibility.PRIVATE,
        )

        store.save(player1_memory)
        store.save(player2_memory)

        retriever = MemoryRetriever(store=store)

        p1_memories = retriever.retrieve(
            session_id="session-1",
            actor_id="player-1",
            current_turn=5,
        )
        p2_memories = retriever.retrieve(
            session_id="session-1",
            actor_id="player-2",
            current_turn=5,
        )

        assert len(p1_memories) == 1
        assert p1_memories[0].id == "mem-p1"
        assert len(p2_memories) == 1
        assert p2_memories[0].id == "mem-p2"

    def test_isolation_between_sessions(self) -> None:
        """Memories should be isolated per session."""
        store = InMemoryMemoryStore()

        session1_memory = MemoryEntry(
            id="mem-s1",
            session_id="session-1",
            actor_id="player-1",
            memory_type=MemoryType.OBSERVATION,
            text="Session 1 observation",
            importance=5,
            tags=[],
            created_at_turn=3,
            visibility=Visibility.PRIVATE,
        )
        session2_memory = MemoryEntry(
            id="mem-s2",
            session_id="session-2",
            actor_id="player-1",
            memory_type=MemoryType.OBSERVATION,
            text="Session 2 observation",
            importance=5,
            tags=[],
            created_at_turn=3,
            visibility=Visibility.PRIVATE,
        )

        store.save(session1_memory)
        store.save(session2_memory)

        retriever = MemoryRetriever(store=store)

        s1_memories = retriever.retrieve(
            session_id="session-1",
            actor_id="player-1",
            current_turn=5,
        )
        s2_memories = retriever.retrieve(
            session_id="session-2",
            actor_id="player-1",
            current_turn=5,
        )

        assert len(s1_memories) == 1
        assert s1_memories[0].id == "mem-s1"
        assert len(s2_memories) == 1
        assert s2_memories[0].id == "mem-s2"


class TestAgentRuntimeEndpoints:
    def test_validate_output_valid(self, client: TestClient) -> None:
        response = client.post(
            "/validate-output",
            json={"raw_text": json.dumps({"speech": "Hello!", "action": {"type": "defend", "stance": "guard"}})},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert data["turn"] is not None

    def test_validate_output_invalid(self, client: TestClient) -> None:
        response = client.post(
            "/validate-output",
            json={"raw_text": "not valid json"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is False

    def test_build_context(self, client: TestClient, sample_state: GameState) -> None:
        response = client.post(
            "/build-context",
            json={
                "session_id": "session-1",
                "agent_id": "agent-1",
                "actor_id": "player-1",
                "actor_name": "Hero",
                "role": "player",
                "goals": ["Win the battle"],
                "state": sample_state.model_dump(mode="json"),
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "context" in data
        assert data["context"]["identity"]["name"] == "Hero"

    def test_get_traces(self, client: TestClient) -> None:
        response = client.get("/traces")
        assert response.status_code == 200
        data = response.json()
        assert "traces" in data
        assert "count" in data
