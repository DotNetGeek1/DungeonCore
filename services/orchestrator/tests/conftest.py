"""Shared fixtures for orchestrator tests."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from shared_config.settings import ServiceSettings
from shared_schemas.actions import AttackAction, DefendAction, PlayerTurn
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

from app.fixtures.mvp_scenario import create_mvp_game_state
from app.service_integration import (
    InvokeAgentResponse,
    ResolveActionResponse,
    StatePatch,
    DiceRoll,
    ValidateActionResponse,
    CreateMessageResponse,
    ServiceClients,
)


@pytest.fixture
def settings() -> ServiceSettings:
    return ServiceSettings.for_service("orchestrator-test", 8001)


@pytest.fixture
def mvp_state() -> GameState:
    return create_mvp_game_state("test-campaign", "test-session")


@pytest.fixture
def mock_agent_runtime_client() -> AsyncMock:
    client = AsyncMock()
    client.invoke_agent = AsyncMock(return_value=InvokeAgentResponse(
        success=True,
        turn=PlayerTurn(
            thought="I should attack the goblin.",
            speech="For glory!",
            action=AttackAction(type=ActionType.ATTACK, target_id="goblin-1"),
        ),
        trace={"steps": ["decision", "action"]},
    ))
    client.health_check = AsyncMock(return_value=True)
    return client


@pytest.fixture
def mock_game_engine_client() -> AsyncMock:
    client = AsyncMock()
    client.validate_action = AsyncMock(return_value=ValidateActionResponse(
        valid=True,
        errors=[],
        warnings=[],
    ))
    client.resolve_action = AsyncMock(return_value=ResolveActionResponse(
        success=True,
        action_type=ActionType.ATTACK,
        description="The fighter strikes the goblin for 7 damage.",
        dice_rolls=[
            DiceRoll(die="d20", value=15, modifier=5, total=20),
            DiceRoll(die="d8", value=5, modifier=2, total=7),
        ],
        state_patches=[
            StatePatch(
                patch_type="damage",
                target_id="goblin-1",
                field="hp",
                old_value=7,
                new_value=0,
            ),
        ],
        hit=True,
        damage=7,
    ))
    client.health_check = AsyncMock(return_value=True)
    return client


@pytest.fixture
def mock_communication_client() -> AsyncMock:
    client = AsyncMock()
    client.create_message = AsyncMock(return_value=CreateMessageResponse(
        success=True,
        message=None,
    ))
    client.register_session = AsyncMock(return_value=True)
    client.get_messages = AsyncMock(return_value=[])
    client.health_check = AsyncMock(return_value=True)
    return client


@pytest.fixture
def mock_service_clients(
    mock_agent_runtime_client: AsyncMock,
    mock_game_engine_client: AsyncMock,
    mock_communication_client: AsyncMock,
) -> MagicMock:
    clients = MagicMock(spec=ServiceClients)
    clients.agent_runtime = mock_agent_runtime_client
    clients.game_engine = mock_game_engine_client
    clients.communication = mock_communication_client
    clients.http_client = AsyncMock()
    clients.close = AsyncMock()
    clients.check_all_health = AsyncMock(return_value={
        "agent_runtime": True,
        "game_engine": True,
        "communication": True,
    })
    return clients
