from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query, Request, status
from pydantic import BaseModel

from shared_schemas import (
    ActionSubmissionRequest,
    ActionSubmissionResponse,
    CreateSessionRequest,
    CreateSessionResponse,
    GameState,
    GetEventHistoryResponse,
    GetSessionStateResponse,
    GetVisibleMessagesResponse,
    OperatorCommandRequest,
    OperatorCommandResponse,
    OverrideActionRequest,
    OverrideActionResponse,
    RerunNarrationRequest,
    RerunNarrationResponse,
    StateEditRequest,
    StateEditResponse,
    TakeoverRequest,
    TakeoverResponse,
)
from shared_schemas.api import SessionSummary
from shared_schemas.enums import (
    ActorRole,
    OperatorCommandType,
    ScenePhase,
    SessionStatus,
    Visibility,
)
from shared_schemas.state import CharacterState, NpcState, ObjectiveState, SceneState, TurnState, VisibilityScope

router = APIRouter()


def _generate_id() -> str:
    return str(uuid.uuid4())


def _mock_initial_state(
    campaign_id: str,
    session_id: str,
    scene_id: str,
    player_ids: list[str],
    npc_ids: list[str],
) -> GameState:
    characters = {}
    for i, pid in enumerate(player_ids):
        characters[pid] = CharacterState(
            actor_id=pid,
            name=f"Hero_{i + 1}",
            role=ActorRole.PLAYER,
            hp=20,
            max_hp=20,
            ac=15,
            position=None,
            status_effects=[],
            inventory=["sword", "shield"],
            spell_slots={},
            visibility_scope=VisibilityScope(visibility=Visibility.PUBLIC),
        )

    npcs = {}
    for i, nid in enumerate(npc_ids):
        npcs[nid] = NpcState(
            actor_id=nid,
            name=f"Goblin_{i + 1}",
            role=ActorRole.NPC,
            hp=7,
            max_hp=7,
            ac=12,
            position=None,
            status_effects=[],
            inventory=["dagger"],
            spell_slots={},
            disposition="hostile",
            visibility_scope=VisibilityScope(visibility=Visibility.PUBLIC),
        )

    return GameState(
        campaign_id=campaign_id,
        session_id=session_id,
        scene=SceneState(
            scene_id=scene_id,
            name="The First Encounter",
            summary="A dimly lit dungeon corridor where danger lurks.",
            turn_number=1,
            active_actor_id=player_ids[0] if player_ids else None,
            phase=ScenePhase.SCENE_INTRO,
        ),
        turn=TurnState(
            turn_number=1,
            round_number=1,
            active_actor_id=player_ids[0] if player_ids else None,
            phase=ScenePhase.SCENE_INTRO,
            discussion_open=False,
            max_discussion_messages=3,
            remaining_discussion_messages=3,
        ),
        characters=characters,
        npcs=npcs,
        objectives=[
            ObjectiveState(
                objective_id="obj-1",
                label="Defeat the goblins",
                status="active",
                summary="Clear the dungeon of goblin invaders.",
            )
        ],
        flags={},
    )


SESSION_STORE: dict[str, tuple[SessionSummary, GameState]] = {}


@router.post("", response_model=CreateSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(request: Request, body: CreateSessionRequest) -> CreateSessionResponse:
    session_id = _generate_id()

    player_ids = body.player_character_ids or [_generate_id() for _ in range(2)]
    npc_ids = body.npc_ids or [_generate_id()]

    state = _mock_initial_state(
        campaign_id=body.campaign_id,
        session_id=session_id,
        scene_id=body.scene_id,
        player_ids=player_ids,
        npc_ids=npc_ids,
    )

    summary = SessionSummary(
        session_id=session_id,
        campaign_id=body.campaign_id,
        scene_id=body.scene_id,
        status=SessionStatus.RUNNING,
    )

    SESSION_STORE[session_id] = (summary, state)

    return CreateSessionResponse(session=summary, state=state)


@router.get("/{session_id}/state", response_model=GetSessionStateResponse)
async def get_session_state(
    request: Request,
    session_id: Annotated[str, Path(description="The session identifier")],
) -> GetSessionStateResponse:
    if session_id not in SESSION_STORE:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    _, state = SESSION_STORE[session_id]
    return GetSessionStateResponse(session_id=session_id, state=state)


@router.get("/{session_id}/events")
async def get_event_history(
    request: Request,
    session_id: Annotated[str, Path(description="The session identifier")],
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    event_type: Annotated[str | None, Query()] = None,
    actor_id: Annotated[str | None, Query()] = None,
) -> dict:
    """Proxy to orchestrator event store. Returns stored events for the session."""
    if session_id not in SESSION_STORE:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    return {
        "session_id": session_id,
        "events": [],
        "total": 0,
        "_note": "Gateway stub. Real events served by orchestrator at /sessions/{id}/events",
    }


@router.get("/{session_id}/replay")
async def get_replay_data(
    request: Request,
    session_id: Annotated[str, Path(description="The session identifier")],
) -> dict:
    """Proxy to orchestrator replay endpoint."""
    if session_id not in SESSION_STORE:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    return {
        "session_id": session_id,
        "initial_state": None,
        "events": [],
        "total_events": 0,
        "total_turns": 0,
        "_note": "Gateway stub. Real replay data served by orchestrator.",
    }


@router.get("/{session_id}/messages", response_model=GetVisibleMessagesResponse)
async def get_visible_messages(
    request: Request,
    session_id: Annotated[str, Path(description="The session identifier")],
    actor_id: Annotated[str | None, Query(description="Filter messages visible to this actor")] = None,
) -> GetVisibleMessagesResponse:
    if session_id not in SESSION_STORE:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    return GetVisibleMessagesResponse(
        session_id=session_id,
        messages=[],
    )


@router.post("/{session_id}/pause", response_model=OperatorCommandResponse)
async def pause_session(
    request: Request,
    session_id: Annotated[str, Path(description="The session identifier")],
    body: OperatorCommandRequest,
) -> OperatorCommandResponse:
    if session_id not in SESSION_STORE:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    summary, state = SESSION_STORE[session_id]

    if summary.status == SessionStatus.PAUSED:
        return OperatorCommandResponse(
            session_id=session_id,
            command_type=OperatorCommandType.PAUSE,
            accepted=False,
            status=summary.status,
            event=None,
        )

    new_summary = SessionSummary(
        session_id=summary.session_id,
        campaign_id=summary.campaign_id,
        scene_id=summary.scene_id,
        status=SessionStatus.PAUSED,
    )
    SESSION_STORE[session_id] = (new_summary, state)

    return OperatorCommandResponse(
        session_id=session_id,
        command_type=OperatorCommandType.PAUSE,
        accepted=True,
        status=SessionStatus.PAUSED,
        event=None,
    )


@router.post("/{session_id}/resume", response_model=OperatorCommandResponse)
async def resume_session(
    request: Request,
    session_id: Annotated[str, Path(description="The session identifier")],
    body: OperatorCommandRequest,
) -> OperatorCommandResponse:
    if session_id not in SESSION_STORE:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    summary, state = SESSION_STORE[session_id]

    if summary.status != SessionStatus.PAUSED:
        return OperatorCommandResponse(
            session_id=session_id,
            command_type=OperatorCommandType.RESUME,
            accepted=False,
            status=summary.status,
            event=None,
        )

    new_summary = SessionSummary(
        session_id=summary.session_id,
        campaign_id=summary.campaign_id,
        scene_id=summary.scene_id,
        status=SessionStatus.RUNNING,
    )
    SESSION_STORE[session_id] = (new_summary, state)

    return OperatorCommandResponse(
        session_id=session_id,
        command_type=OperatorCommandType.RESUME,
        accepted=True,
        status=SessionStatus.RUNNING,
        event=None,
    )


@router.post("/{session_id}/takeover", response_model=TakeoverResponse)
async def takeover_character(
    request: Request,
    session_id: Annotated[str, Path(description="The session identifier")],
    body: TakeoverRequest,
) -> TakeoverResponse:
    """Proxy takeover to orchestrator."""
    if session_id not in SESSION_STORE:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    return TakeoverResponse(
        session_id=session_id,
        actor_id=body.actor_id,
        accepted=True,
        new_controller="human",
        message=f"Takeover accepted for {body.actor_id} (gateway stub - orchestrator handles actual state)",
    )


@router.post("/{session_id}/release-takeover", response_model=TakeoverResponse)
async def release_takeover(
    request: Request,
    session_id: Annotated[str, Path(description="The session identifier")],
    body: TakeoverRequest,
) -> TakeoverResponse:
    """Proxy release-takeover to orchestrator."""
    if session_id not in SESSION_STORE:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    return TakeoverResponse(
        session_id=session_id,
        actor_id=body.actor_id,
        accepted=True,
        new_controller="agent",
        message=f"Released {body.actor_id} back to agent control",
    )


@router.post("/{session_id}/submit-action", response_model=ActionSubmissionResponse)
async def submit_action(
    request: Request,
    session_id: Annotated[str, Path(description="The session identifier")],
    body: ActionSubmissionRequest,
) -> ActionSubmissionResponse:
    """Proxy human action submission to orchestrator."""
    if session_id not in SESSION_STORE:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    return ActionSubmissionResponse(
        session_id=session_id,
        accepted=True,
        action_status="queued",
        normalized_action=body.turn.action,
    )


@router.post("/{session_id}/override-action", response_model=OverrideActionResponse)
async def override_action(
    request: Request,
    session_id: Annotated[str, Path(description="The session identifier")],
    body: OverrideActionRequest,
) -> OverrideActionResponse:
    """Proxy director action override to orchestrator."""
    if session_id not in SESSION_STORE:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    return OverrideActionResponse(
        session_id=session_id,
        accepted=True,
        message="Action override queued",
    )


@router.patch("/{session_id}/state", response_model=StateEditResponse)
async def edit_state(
    request: Request,
    session_id: Annotated[str, Path(description="The session identifier")],
    body: StateEditRequest,
) -> StateEditResponse:
    """Proxy director state edit to orchestrator."""
    if session_id not in SESSION_STORE:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    return StateEditResponse(
        session_id=session_id,
        accepted=True,
        patches_applied=len(body.patches),
        message=f"Applied {len(body.patches)} patches (gateway stub)",
    )


@router.post("/{session_id}/rerun-narration", response_model=RerunNarrationResponse)
async def rerun_narration(
    request: Request,
    session_id: Annotated[str, Path(description="The session identifier")],
    body: RerunNarrationRequest,
) -> RerunNarrationResponse:
    """Proxy narration re-run to orchestrator."""
    if session_id not in SESSION_STORE:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    return RerunNarrationResponse(
        session_id=session_id,
        accepted=True,
        message="Narration re-run queued (gateway stub)",
    )
