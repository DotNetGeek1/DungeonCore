import asyncio
import json as json_module
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Annotated, AsyncGenerator, Literal
import uuid

logger = logging.getLogger(__name__)

import uvicorn
from fastapi import APIRouter, FastAPI, HTTPException, Path, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from shared_config.connections import (
    check_postgres_health,
    check_rabbitmq_health,
    check_redis_health,
    create_postgres_engine,
    create_redis_client,
    run_alembic_migrations,
)
from shared_config.coordination import RedisCoordinator
from shared_config.persistence import (
    AIInvocationRepository,
    EventRepository,
    SessionRepository,
    StateSnapshotRepository,
    metadata as db_metadata,
)
from shared_config.settings import ServiceSettings
from shared_schemas.enums import ActionType, ActorRole, ControllerType, ScenePhase, Visibility
from shared_schemas.state import (
    CharacterState,
    GameState,
    NpcState,
    ObjectiveState,
    SceneState,
    TurnState,
    VisibilityScope,
)
from shared_schemas.actions import PlayerTurn
from shared_schemas.api import (
    ActionSubmissionRequest,
    ActionSubmissionResponse,
    OverrideActionRequest,
    OverrideActionResponse,
    RerunNarrationRequest,
    RerunNarrationResponse,
    StateEditRequest,
    StateEditResponse,
    TakeoverRequest,
    TakeoverResponse,
)
from shared_schemas.enums import ActionSubmissionSource

from .event_store import InMemoryEventStore, PersistentEventStore
from .fixtures.mvp_scenario import create_mvp_game_state, MVP_SCENE_CONFIG
from .human_interaction import HumanActionStore, OverrideStore, LastResolutionStore
from .service_integration import ServiceClients, InvokeAgentResponse, apply_state_patches, StatePatch
from .state_machine import StateMachine, create_phase_context
from .trace_logger import TurnTraceLogger
from .turn_runner import TurnRunner, create_turn_runner


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings: ServiceSettings = app.state.settings
    print(f"Starting {settings.service_name} on port {settings.port}")

    try:
        redis_client = create_redis_client(settings)
        coordinator = RedisCoordinator(redis_client)
        app.state.coordinator = coordinator
    except Exception:
        app.state.coordinator = None

    # Initialize PostgreSQL repositories for session persistence
    try:
        db_engine = create_postgres_engine(settings)
        # Run Alembic migrations to ensure schema is up to date
        run_alembic_migrations(db_engine)
        app.state.session_repo = SessionRepository(db_engine)
        app.state.event_repo = EventRepository(db_engine)
        app.state.snapshot_repo = StateSnapshotRepository(db_engine)
        app.state.ai_invocation_repo = AIInvocationRepository(db_engine)
        app.state.db_engine = db_engine
        print("PostgreSQL persistence initialized successfully")
    except Exception as e:
        logger.warning("PostgreSQL persistence unavailable: %s", e)
        app.state.session_repo = None
        app.state.event_repo = None
        app.state.snapshot_repo = None
        app.state.ai_invocation_repo = None
        app.state.db_engine = None

    service_clients = ServiceClients.create(
        agent_runtime_url=f"http://agent-runtime:{settings.agent_runtime_port}",
        game_engine_url=f"http://game-engine:{settings.game_engine_port}",
        communication_url=f"http://communication-service:{settings.communication_service_port}",
    )
    app.state.service_clients = service_clients

    human_action_store = HumanActionStore()
    override_store = OverrideStore()
    last_resolution_store = LastResolutionStore()
    memory_event_store = InMemoryEventStore()
    trace_logger = TurnTraceLogger()

    # Create persistent event store that wraps in-memory and DB storage
    event_store = PersistentEventStore(
        memory_store=memory_event_store,
        event_repo=app.state.event_repo,
    )

    app.state.human_action_store = human_action_store
    app.state.override_store = override_store
    app.state.last_resolution_store = last_resolution_store
    app.state.event_store = event_store
    app.state.memory_event_store = memory_event_store
    app.state.trace_logger = trace_logger

    app.state.turn_runner = create_turn_runner(
        coordinator=app.state.coordinator,
        clients=service_clients,
        publisher=event_store,
        human_action_store=human_action_store,
        override_store=override_store,
        last_resolution_store=last_resolution_store,
        trace_logger=trace_logger,
        ai_invocation_repo=app.state.ai_invocation_repo,
    )
    app.state.sessions = {}

    yield

    await service_clients.close()
    print(f"Shutting down {settings.service_name}")


def create_app(settings: ServiceSettings | None = None) -> FastAPI:
    if settings is None:
        settings = ServiceSettings.for_service("orchestrator", 8001)

    app = FastAPI(
        title="DungeonCore Orchestrator",
        description="Turn orchestration and state machine for DungeonCore",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.settings = settings

    router = APIRouter()

    class DependencyStatus(BaseModel):
        postgres: bool
        redis: bool
        rabbitmq: bool

    class HealthResponse(BaseModel):
        service: str
        status: Literal["ok", "degraded"]
        port: int
        dependencies: DependencyStatus

    @router.get("/health", response_model=HealthResponse)
    async def health_check(request: Request) -> HealthResponse:
        settings: ServiceSettings = request.app.state.settings
        deps = DependencyStatus(
            postgres=check_postgres_health(settings),
            redis=check_redis_health(settings),
            rabbitmq=check_rabbitmq_health(settings),
        )
        all_healthy = deps.postgres and deps.redis and deps.rabbitmq
        return HealthResponse(
            service=settings.service_name,
            status="ok" if all_healthy else "degraded",
            port=settings.port,
            dependencies=deps,
        )

    class StartSessionRequest(BaseModel):
        campaign_id: str
        scene_id: str
        player_ids: list[str] = Field(default_factory=list)
        npc_ids: list[str] = Field(default_factory=list)
        use_mvp_scenario: bool = Field(
            default=False,
            description="Use the MVP Goblin Ambush scenario with predefined characters",
        )
        generate_dynamic_map: bool = Field(
            default=False,
            description="Generate a unique dungeon map dynamically using AI",
        )
        story_genre: str | None = Field(
            default=None,
            description="Story genre: classic_fantasy, dark_fantasy, horror, mystery, heroic, survival",
        )
        story_themes: list[str] | None = Field(
            default=None,
            description="Story themes to include (e.g., exploration, combat, mystery)",
        )
        map_complexity: str | None = Field(
            default=None,
            description="Map complexity: simple, medium, complex",
        )

    class SessionStateResponse(BaseModel):
        session_id: str
        state: GameState
        phase: ScenePhase

    class RunTurnRequest(BaseModel):
        force: bool = False

    class TurnResultResponse(BaseModel):
        success: bool
        session_id: str
        turn_number: int
        phase: ScenePhase
        events_count: int
        events: list[dict] = Field(default_factory=list)
        errors: list[str] = Field(default_factory=list)

    class FullTurnResultResponse(BaseModel):
        success: bool
        session_id: str
        turn_number: int
        phase: ScenePhase
        events_count: int
        events: list[dict] = Field(default_factory=list)
        state: GameState
        errors: list[str] = Field(default_factory=list)

    def _create_initial_state(
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

    def _persist_session_to_db(request: Request, state: GameState, status_str: str = "RUNNING") -> None:
        """Persist session to PostgreSQL if available."""
        session_repo: SessionRepository | None = request.app.state.session_repo
        snapshot_repo: StateSnapshotRepository | None = request.app.state.snapshot_repo

        if session_repo is not None:
            try:
                # Ensure campaign exists (FK dependency)
                session_repo.ensure_campaign(
                    campaign_id=state.campaign_id,
                    name=f"Campaign {state.campaign_id[:8]}",
                    payload={"created_from_session": state.session_id},
                )
                # Ensure scene exists (FK dependency)
                session_repo.ensure_scene(
                    scene_id=state.scene.scene_id,
                    campaign_id=state.campaign_id,
                    name=state.scene.name,
                    payload=state.scene.model_dump(mode="json"),
                )
                # Now create the session
                session_payload = {
                    "session": {
                        "session_id": state.session_id,
                        "campaign_id": state.campaign_id,
                        "scene_id": state.scene.scene_id,
                        "status": status_str,
                    },
                    "state": state.model_dump(mode="json"),
                }
                session_repo.create_session(session_payload)
                logger.info("Session %s persisted to database", state.session_id)
            except Exception as e:
                logger.warning("Failed to persist session to DB: %s", e)

        if snapshot_repo is not None:
            try:
                snapshot_repo.save_game_state(state)
            except Exception as e:
                logger.warning("Failed to save initial snapshot: %s", e)

    def _save_state_snapshot(request: Request, state: GameState) -> None:
        """Save a state snapshot to PostgreSQL if available."""
        snapshot_repo: StateSnapshotRepository | None = request.app.state.snapshot_repo
        if snapshot_repo is not None:
            try:
                snapshot_repo.save_game_state(state)
            except Exception as e:
                logger.warning("Failed to save state snapshot: %s", e)

    @router.post("/sessions/start", response_model=SessionStateResponse, status_code=status.HTTP_201_CREATED)
    async def start_session(request: Request, body: StartSessionRequest) -> SessionStateResponse:
        from .fixtures.mvp_scenario import StoryConfig, StoryGenre, DifficultyLevel, MapComplexity

        session_id = str(uuid.uuid4())

        # Build story config from request parameters
        story_config = None
        if body.story_genre or body.story_themes or body.map_complexity:
            try:
                genre = StoryGenre(body.story_genre) if body.story_genre else StoryGenre.CLASSIC_FANTASY
            except ValueError:
                genre = StoryGenre.CLASSIC_FANTASY
            try:
                map_comp = MapComplexity(body.map_complexity) if body.map_complexity else MapComplexity.MEDIUM
            except ValueError:
                map_comp = MapComplexity.MEDIUM

            story_config = StoryConfig(
                genre=genre,
                themes=body.story_themes or ["exploration", "combat"],
                map_complexity=map_comp,
            )

        if body.use_mvp_scenario:
            state = create_mvp_game_state(
                campaign_id=body.campaign_id,
                session_id=session_id,
                story_config=story_config,
            )
        else:
            player_ids = body.player_ids or [str(uuid.uuid4()) for _ in range(2)]
            npc_ids = body.npc_ids or [str(uuid.uuid4())]

            state = _create_initial_state(
                campaign_id=body.campaign_id,
                session_id=session_id,
                scene_id=body.scene_id,
                player_ids=player_ids,
                npc_ids=npc_ids,
            )

        # Enable dynamic map generation if requested
        if body.generate_dynamic_map:
            flags = dict(state.flags)
            flags["generate_dynamic_map"] = True
            state = state.model_copy(update={"flags": flags, "dungeon_map": None})

        request.app.state.sessions[session_id] = state
        es: InMemoryEventStore = request.app.state.event_store
        es.store_initial_state(session_id, state)

        _persist_session_to_db(request, state)

        return SessionStateResponse(
            session_id=session_id,
            state=state,
            phase=state.scene.phase,
        )

    @router.post("/sessions/start-mvp", response_model=SessionStateResponse, status_code=status.HTTP_201_CREATED)
    async def start_mvp_session(request: Request) -> SessionStateResponse:
        """Start a new session using the MVP Goblin Ambush scenario."""
        session_id = str(uuid.uuid4())
        campaign_id = f"campaign-{str(uuid.uuid4())[:8]}"

        state = create_mvp_game_state(
            campaign_id=campaign_id,
            session_id=session_id,
        )

        request.app.state.sessions[session_id] = state
        es: InMemoryEventStore = request.app.state.event_store
        es.store_initial_state(session_id, state)

        _persist_session_to_db(request, state)

        return SessionStateResponse(
            session_id=session_id,
            state=state,
            phase=state.scene.phase,
        )

    @router.get("/sessions/{session_id}", response_model=SessionStateResponse)
    async def get_session(
        request: Request,
        session_id: Annotated[str, Path(description="The session identifier")],
    ) -> SessionStateResponse:
        sessions = request.app.state.sessions
        if session_id not in sessions:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

        state = sessions[session_id]
        return SessionStateResponse(
            session_id=session_id,
            state=state,
            phase=state.scene.phase,
        )

    class SessionSummary(BaseModel):
        session_id: str
        campaign_id: str
        scene_id: str
        scene_name: str | None = None
        status: str  # lowercase: running, paused, completed, error, created
        turn_number: int | None = None
        phase: ScenePhase | None = None
        started_at: str | None = None
        paused_at: str | None = None
        source: str  # 'memory' or 'database'

    class SessionListResponse(BaseModel):
        sessions: list[SessionSummary]
        total: int
        limit: int
        offset: int

    @router.get("/sessions", response_model=SessionListResponse)
    async def list_sessions(
        request: Request,
        status_filter: Annotated[str | None, Query(alias="status", description="Filter by status (running, paused, etc.)")] = None,
        campaign_id: Annotated[str | None, Query(description="Filter by campaign ID")] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> SessionListResponse:
        """List all sessions from memory and database."""
        sessions = request.app.state.sessions
        session_repo: SessionRepository | None = request.app.state.session_repo

        result_sessions: list[SessionSummary] = []
        seen_ids: set[str] = set()

        # Normalize status filter to uppercase for DB queries, but accept lowercase from frontend
        db_status_filter = status_filter.upper() if status_filter else None

        # First, add all in-memory sessions (these are always "running")
        for sid, state in sessions.items():
            # In-memory sessions are running; skip if filtering for non-running status
            if status_filter and status_filter.lower() != "running":
                continue
            if campaign_id and state.campaign_id != campaign_id:
                continue

            result_sessions.append(SessionSummary(
                session_id=sid,
                campaign_id=state.campaign_id,
                scene_id=state.scene.scene_id,
                scene_name=state.scene.name,
                status="running",
                turn_number=state.turn.turn_number,
                phase=state.scene.phase,
                source="memory",
            ))
            seen_ids.add(sid)

        # Then, add sessions from database that aren't already in memory
        if session_repo is not None:
            try:
                db_sessions = session_repo.list_sessions(
                    status=db_status_filter,
                    campaign_id=campaign_id,
                    limit=limit + len(seen_ids),
                    offset=offset,
                )

                for db_sess in db_sessions:
                    sid = db_sess["session_id"]
                    if sid in seen_ids:
                        continue

                    payload = db_sess.get("payload", {})
                    state_data = payload.get("state", {})
                    scene_data = state_data.get("scene", {})
                    turn_data = state_data.get("turn", {})

                    # Convert DB status (uppercase) to lowercase for frontend
                    db_status = db_sess.get("status", "RUNNING")
                    frontend_status = db_status.lower() if db_status else "running"

                    result_sessions.append(SessionSummary(
                        session_id=sid,
                        campaign_id=db_sess["campaign_id"],
                        scene_id=db_sess["scene_id"],
                        scene_name=scene_data.get("name"),
                        status=frontend_status,
                        turn_number=turn_data.get("turn_number"),
                        phase=ScenePhase(scene_data["phase"]) if scene_data.get("phase") else None,
                        started_at=db_sess.get("created_at"),
                        paused_at=db_sess.get("updated_at") if frontend_status == "paused" else None,
                        source="database",
                    ))
            except Exception as e:
                logger.warning("Failed to list sessions from database: %s", e)

        # Apply pagination to the combined result
        paginated = result_sessions[offset:offset + limit]

        return SessionListResponse(
            sessions=paginated,
            total=len(result_sessions),
            limit=limit,
            offset=offset,
        )

    @router.get("/sessions/{session_id}/history")
    async def get_session_history(
        request: Request,
        session_id: Annotated[str, Path(description="The session identifier")],
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
    ) -> dict:
        """Get session event history from database."""
        event_repo: EventRepository | None = request.app.state.event_repo
        snapshot_repo: StateSnapshotRepository | None = request.app.state.snapshot_repo

        result: dict = {
            "session_id": session_id,
            "events": [],
            "snapshots": [],
            "from_database": False,
        }

        if event_repo is not None:
            try:
                events = event_repo.list_for_session(session_id, limit=limit)
                result["events"] = events
                result["from_database"] = True
            except Exception as e:
                logger.warning("Failed to get events from DB: %s", e)

        if snapshot_repo is not None:
            try:
                snapshots = snapshot_repo.list_snapshots(session_id, limit=20)
                result["snapshots"] = snapshots
            except Exception as e:
                logger.warning("Failed to get snapshots from DB: %s", e)

        return result

    @router.get("/sessions/{session_id}/transcript")
    async def get_session_transcript(
        request: Request,
        session_id: Annotated[str, Path(description="The session identifier")],
    ) -> dict:
        """Get a human-readable narrative transcript of the session."""
        es: InMemoryEventStore = request.app.state.event_store
        event_repo: EventRepository | None = request.app.state.event_repo

        events: list[dict] = []

        # Try in-memory first
        try:
            events = es.list_events(session_id, limit=500)
        except Exception:
            pass

        # Fall back to database
        if not events and event_repo is not None:
            try:
                events = event_repo.list_for_session(session_id, limit=500)
            except Exception as e:
                logger.warning("Failed to get events for transcript: %s", e)

        # Build narrative from narration events
        transcript_lines: list[dict] = []
        for evt in events:
            evt_type = evt.get("event_type", "")
            payload = evt.get("payload", {})

            if evt_type == "narration.emitted":
                transcript_lines.append({
                    "type": "narration",
                    "turn": evt.get("turn_number"),
                    "text": payload.get("narration_text", ""),
                })
            elif evt_type == "action.resolved":
                transcript_lines.append({
                    "type": "action",
                    "turn": evt.get("turn_number"),
                    "actor": payload.get("actor_id"),
                    "action_type": payload.get("action_type"),
                    "description": payload.get("description", ""),
                })
            elif evt_type == "message.created":
                channel = payload.get("channel", "")
                if channel in ("in_character", "table_talk"):
                    transcript_lines.append({
                        "type": "dialogue",
                        "turn": evt.get("turn_number"),
                        "speaker": payload.get("sender_name", payload.get("sender_id")),
                        "channel": channel,
                        "text": payload.get("content", ""),
                    })

        return {
            "session_id": session_id,
            "transcript": transcript_lines,
            "total_entries": len(transcript_lines),
        }

    def _serialize_events(events: list[object]) -> list[dict]:
        """Serialize events to JSON-compatible dictionaries."""
        serialized = []
        for event in events:
            if hasattr(event, "model_dump"):
                serialized.append(event.model_dump(mode="json"))
            elif hasattr(event, "__dict__"):
                serialized.append(event.__dict__)
            else:
                serialized.append({"type": str(type(event).__name__)})
        return serialized

    @router.post("/sessions/{session_id}/turn", response_model=TurnResultResponse)
    async def run_turn(
        request: Request,
        session_id: Annotated[str, Path(description="The session identifier")],
        body: RunTurnRequest,
    ) -> TurnResultResponse:
        """Advance the session by one phase."""
        sessions = request.app.state.sessions
        if session_id not in sessions:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

        state = sessions[session_id]
        turn_runner: TurnRunner = request.app.state.turn_runner

        ctx = create_phase_context(session_id, state)
        result = await turn_runner.run_turn(ctx)

        sessions[session_id] = result.final_state
        _save_state_snapshot(request, result.final_state)

        return TurnResultResponse(
            success=result.success,
            session_id=session_id,
            turn_number=result.final_state.turn.turn_number,
            phase=result.final_state.scene.phase,
            events_count=len(result.events),
            events=_serialize_events(result.events),
            errors=result.errors,
        )

    @router.post("/sessions/{session_id}/full-turn", response_model=FullTurnResultResponse)
    async def run_full_turn(
        request: Request,
        session_id: Annotated[str, Path(description="The session identifier")],
    ) -> FullTurnResultResponse:
        """Run a complete turn cycle through all phases."""
        sessions = request.app.state.sessions
        if session_id not in sessions:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

        state = sessions[session_id]
        turn_runner: TurnRunner = request.app.state.turn_runner

        ctx = create_phase_context(session_id, state)
        result = await turn_runner.run_full_turn_cycle(ctx)

        sessions[session_id] = result.final_state
        _save_state_snapshot(request, result.final_state)

        return FullTurnResultResponse(
            success=result.success,
            session_id=session_id,
            turn_number=result.final_state.turn.turn_number,
            phase=result.final_state.scene.phase,
            events_count=len(result.events),
            events=_serialize_events(result.events),
            state=result.final_state,
            errors=result.errors,
        )

    @router.post("/sessions/{session_id}/advance-phase", response_model=SessionStateResponse)
    async def advance_phase(
        request: Request,
        session_id: Annotated[str, Path(description="The session identifier")],
    ) -> SessionStateResponse:
        """Advance the session by one phase (alias for /turn)."""
        sessions = request.app.state.sessions
        if session_id not in sessions:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

        state = sessions[session_id]
        turn_runner: TurnRunner = request.app.state.turn_runner

        ctx = create_phase_context(session_id, state)
        result = await turn_runner.run_turn(ctx)

        sessions[session_id] = result.final_state

        return SessionStateResponse(
            session_id=session_id,
            state=result.final_state,
            phase=result.final_state.scene.phase,
        )

    # --- Human-in-the-Loop endpoints ---

    @router.post("/sessions/{session_id}/takeover", response_model=TakeoverResponse)
    async def takeover_character(
        request: Request,
        session_id: Annotated[str, Path(description="The session identifier")],
        body: TakeoverRequest,
    ) -> TakeoverResponse:
        """Switch a character from agent to human control."""
        sessions = request.app.state.sessions
        if session_id not in sessions:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

        state = sessions[session_id]
        actor_id = body.actor_id

        if actor_id not in state.characters:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Actor '{actor_id}' not found in characters")

        char = state.characters[actor_id]
        previous_controller = char.controller
        updated_char = char.model_copy(update={"controller": ControllerType.HUMAN})

        characters = dict(state.characters)
        characters[actor_id] = updated_char
        sessions[session_id] = state.model_copy(update={"characters": characters})

        return TakeoverResponse(
            session_id=session_id,
            actor_id=actor_id,
            accepted=True,
            new_controller=ControllerType.HUMAN,
            message=f"Character '{actor_id}' switched from {previous_controller} to human control",
        )

    @router.post("/sessions/{session_id}/release-takeover", response_model=TakeoverResponse)
    async def release_takeover(
        request: Request,
        session_id: Annotated[str, Path(description="The session identifier")],
        body: TakeoverRequest,
    ) -> TakeoverResponse:
        """Return a character from human to agent control."""
        sessions = request.app.state.sessions
        if session_id not in sessions:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

        state = sessions[session_id]
        actor_id = body.actor_id

        if actor_id not in state.characters:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Actor '{actor_id}' not found in characters")

        char = state.characters[actor_id]
        previous_controller = char.controller
        updated_char = char.model_copy(update={"controller": ControllerType.AGENT})

        characters = dict(state.characters)
        characters[actor_id] = updated_char
        sessions[session_id] = state.model_copy(update={"characters": characters})

        return TakeoverResponse(
            session_id=session_id,
            actor_id=actor_id,
            accepted=True,
            new_controller=ControllerType.AGENT,
            message=f"Character '{actor_id}' returned to agent control",
        )

    @router.post("/sessions/{session_id}/submit-action", response_model=ActionSubmissionResponse)
    async def submit_human_action(
        request: Request,
        session_id: Annotated[str, Path(description="The session identifier")],
        body: ActionSubmissionRequest,
    ) -> ActionSubmissionResponse:
        """Submit a human player's action for the current turn."""
        sessions = request.app.state.sessions
        if session_id not in sessions:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

        human_store: HumanActionStore = request.app.state.human_action_store
        pending = human_store.get_pending(session_id)

        if pending is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="No pending human action for this session. The turn may not be awaiting human input.",
            )

        if pending.actor_id != body.actor_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Pending action is for actor '{pending.actor_id}', not '{body.actor_id}'",
            )

        submitted = human_store.submit_action(session_id, body.turn)
        if not submitted:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Failed to submit action")

        return ActionSubmissionResponse(
            session_id=session_id,
            accepted=True,
            action_status="queued",
            normalized_action=body.turn.action,
        )

    # --- Director Override endpoints ---

    @router.post("/sessions/{session_id}/override-action", response_model=OverrideActionResponse)
    async def override_action(
        request: Request,
        session_id: Annotated[str, Path(description="The session identifier")],
        body: OverrideActionRequest,
    ) -> OverrideActionResponse:
        """Replace the pending action before resolution (director only)."""
        sessions = request.app.state.sessions
        if session_id not in sessions:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

        state = sessions[session_id]
        phase = state.scene.phase
        if phase not in (ScenePhase.ACTION_COMMIT, ScenePhase.RESOLUTION):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Override only allowed in ACTION_COMMIT or RESOLUTION phase, currently in {phase}",
            )

        override_store: OverrideStore = request.app.state.override_store
        override_store.set_override(session_id, body.turn)

        return OverrideActionResponse(
            session_id=session_id,
            accepted=True,
            message=f"Action override queued for session {session_id}",
        )

    @router.patch("/sessions/{session_id}/state", response_model=StateEditResponse)
    async def edit_state(
        request: Request,
        session_id: Annotated[str, Path(description="The session identifier")],
        body: StateEditRequest,
    ) -> StateEditResponse:
        """Apply director state edits (HP, alive, position, flags)."""
        sessions = request.app.state.sessions
        if session_id not in sessions:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

        state = sessions[session_id]
        ALLOWED_FIELDS = {"hp", "alive", "position", "status_effects"}
        patches_applied = 0

        characters = dict(state.characters)
        npcs = dict(state.npcs)
        flags = dict(state.flags)

        for patch in body.patches:
            target_id = patch.get("target_id")
            field_name = patch.get("field")
            value = patch.get("value")

            if not target_id or not field_name:
                continue

            if field_name == "flags":
                if isinstance(value, dict):
                    flags.update(value)
                    patches_applied += 1
                continue

            if field_name not in ALLOWED_FIELDS:
                continue

            if target_id in characters:
                characters[target_id] = characters[target_id].model_copy(update={field_name: value})
                patches_applied += 1
            elif target_id in npcs:
                npcs[target_id] = npcs[target_id].model_copy(update={field_name: value})
                patches_applied += 1

        sessions[session_id] = state.model_copy(update={
            "characters": characters,
            "npcs": npcs,
            "flags": flags,
        })

        return StateEditResponse(
            session_id=session_id,
            accepted=True,
            patches_applied=patches_applied,
            message=f"Applied {patches_applied} state patches",
        )

    @router.post("/sessions/{session_id}/rerun-narration", response_model=RerunNarrationResponse)
    async def rerun_narration(
        request: Request,
        session_id: Annotated[str, Path(description="The session identifier")],
        body: RerunNarrationRequest,
    ) -> RerunNarrationResponse:
        """Re-run DM narration from the last resolution result."""
        sessions = request.app.state.sessions
        if session_id not in sessions:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

        state = sessions[session_id]
        phase = state.scene.phase
        if phase not in (ScenePhase.NARRATION, ScenePhase.REACTION, ScenePhase.TURN_END):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Rerun narration only allowed after NARRATION phase, currently in {phase}",
            )

        last_res_store: LastResolutionStore = request.app.state.last_resolution_store
        resolution_data = last_res_store.get(session_id)

        if resolution_data is None:
            return RerunNarrationResponse(
                session_id=session_id,
                accepted=False,
                message="No resolution data available for re-narration",
            )

        turn_runner: TurnRunner = request.app.state.turn_runner
        try:
            ctx = create_phase_context(session_id, state)
            narration_text = await turn_runner.rerun_narration(ctx, resolution_data)
            return RerunNarrationResponse(
                session_id=session_id,
                accepted=True,
                narration_text=narration_text,
                message="Narration re-run successfully",
            )
        except Exception as e:
            return RerunNarrationResponse(
                session_id=session_id,
                accepted=False,
                message=f"Failed to rerun narration: {str(e)}",
            )

    # --- Observability endpoints ---

    @router.get("/sessions/{session_id}/events")
    async def get_events(
        request: Request,
        session_id: Annotated[str, Path(description="The session identifier")],
        limit: int = 500,
        event_type: str | None = None,
        actor_id: str | None = None,
    ) -> dict:
        """Get stored events for a session."""
        es: InMemoryEventStore = request.app.state.event_store
        events = es.list_events(
            session_id, limit=limit, event_type=event_type, actor_id=actor_id
        )
        return {
            "session_id": session_id,
            "events": events,
            "total": len(events),
        }

    @router.get("/sessions/{session_id}/traces")
    async def get_traces(
        request: Request,
        session_id: Annotated[str, Path(description="The session identifier")],
    ) -> dict:
        """Get structured turn traces for a session (diagnostic, non-canonical)."""
        tl: TurnTraceLogger = request.app.state.trace_logger
        traces = tl.get_traces(session_id)
        return {
            "session_id": session_id,
            "traces": [tl.serialize_trace(t) for t in traces],
            "total": len(traces),
            "_note": "Traces are diagnostic artifacts, not canonical game state.",
        }

    @router.get("/sessions/{session_id}/replay")
    async def get_replay_data(
        request: Request,
        session_id: Annotated[str, Path(description="The session identifier")],
    ) -> dict:
        """Get full event log with initial state for session replay."""
        es: InMemoryEventStore = request.app.state.event_store
        return es.get_replay_data(session_id)

    # --- Route aliases to match frontend client expectations ---

    @router.get("/sessions/{session_id}/state", response_model=SessionStateResponse)
    async def get_session_state(
        request: Request,
        session_id: Annotated[str, Path(description="The session identifier")],
    ) -> SessionStateResponse:
        """Alias for GET /sessions/{id} — frontend uses /state suffix."""
        sessions = request.app.state.sessions
        if session_id not in sessions:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
        state = sessions[session_id]
        return SessionStateResponse(session_id=session_id, state=state, phase=state.scene.phase)

    @router.post("/sessions", response_model=SessionStateResponse, status_code=status.HTTP_201_CREATED)
    async def create_session_alias(request: Request) -> SessionStateResponse:
        """Alias for POST /sessions/start-mvp — frontend calls POST /sessions with no body."""
        session_id = str(uuid.uuid4())
        campaign_id = f"campaign-{str(uuid.uuid4())[:8]}"
        state = create_mvp_game_state(campaign_id=campaign_id, session_id=session_id)
        request.app.state.sessions[session_id] = state
        es: InMemoryEventStore = request.app.state.event_store
        es.store_initial_state(session_id, state)
        _persist_session_to_db(request, state)
        return SessionStateResponse(session_id=session_id, state=state, phase=state.scene.phase)

    class SessionCommandResponse(BaseModel):
        session_id: str
        accepted: bool
        message: str
        status: str | None = None

    @router.post("/sessions/{session_id}/pause", response_model=SessionCommandResponse)
    async def pause_session(
        request: Request,
        session_id: Annotated[str, Path(description="The session identifier")],
    ) -> SessionCommandResponse:
        """Pause a running session, saving state to database."""
        sessions = request.app.state.sessions
        session_repo: SessionRepository | None = request.app.state.session_repo
        snapshot_repo: StateSnapshotRepository | None = request.app.state.snapshot_repo

        if session_id not in sessions:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found in memory")

        state = sessions[session_id]

        # Save final snapshot before pausing
        if snapshot_repo is not None:
            try:
                snapshot_repo.save_game_state(state)
            except Exception as e:
                logger.warning("Failed to save pause snapshot: %s", e)

        # Update session status in DB
        if session_repo is not None:
            try:
                session_payload = {
                    "session": {
                        "session_id": state.session_id,
                        "campaign_id": state.campaign_id,
                        "scene_id": state.scene.scene_id,
                        "status": "PAUSED",
                    },
                    "state": state.model_dump(mode="json"),
                }
                session_repo.update_session_status(session_id, "PAUSED", session_payload)
            except Exception as e:
                logger.warning("Failed to update session status to PAUSED: %s", e)

        # Remove from active in-memory sessions
        del sessions[session_id]

        return SessionCommandResponse(
            session_id=session_id,
            accepted=True,
            message="Session paused and saved to database",
            status="PAUSED",
        )

    @router.post("/sessions/{session_id}/resume", response_model=SessionCommandResponse)
    async def resume_session(
        request: Request,
        session_id: Annotated[str, Path(description="The session identifier")],
    ) -> SessionCommandResponse:
        """Resume a paused session by loading state from database."""
        sessions = request.app.state.sessions
        session_repo: SessionRepository | None = request.app.state.session_repo
        snapshot_repo: StateSnapshotRepository | None = request.app.state.snapshot_repo

        # Check if already in memory
        if session_id in sessions:
            return SessionCommandResponse(
                session_id=session_id,
                accepted=True,
                message="Session already running in memory",
                status="RUNNING",
            )

        # Try to load from database
        state: GameState | None = None

        if snapshot_repo is not None:
            try:
                state = snapshot_repo.get_latest_game_state(session_id)
            except Exception as e:
                logger.warning("Failed to load snapshot from DB: %s", e)

        if state is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found in memory or database",
            )

        # Restore to in-memory sessions
        sessions[session_id] = state

        # Update status in DB
        if session_repo is not None:
            try:
                session_payload = {
                    "session": {
                        "session_id": state.session_id,
                        "campaign_id": state.campaign_id,
                        "scene_id": state.scene.scene_id,
                        "status": "RUNNING",
                    },
                    "state": state.model_dump(mode="json"),
                }
                session_repo.update_session_status(session_id, "RUNNING", session_payload)
            except Exception as e:
                logger.warning("Failed to update session status to RUNNING: %s", e)

        return SessionCommandResponse(
            session_id=session_id,
            accepted=True,
            message=f"Session resumed from turn {state.turn.turn_number}",
            status="RUNNING",
        )

    @router.post("/sessions/{session_id}/inject-event", response_model=SessionCommandResponse)
    async def inject_event(
        request: Request,
        session_id: Annotated[str, Path(description="The session identifier")],
    ) -> SessionCommandResponse:
        sessions = request.app.state.sessions
        if session_id not in sessions:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
        return SessionCommandResponse(session_id=session_id, accepted=True, message="Event injected (stub)")

    @router.get("/sessions/{session_id}/messages")
    async def get_session_messages(
        request: Request,
        session_id: Annotated[str, Path(description="The session identifier")],
        actor_id: str | None = None,
    ) -> dict:
        """Proxy message retrieval to communication service, or return empty list."""
        sessions = request.app.state.sessions
        if session_id not in sessions:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
        clients: ServiceClients | None = request.app.state.service_clients
        if clients:
            try:
                messages = await clients.communication.get_messages(
                    session_id=session_id, viewer_id=actor_id,
                )
                return {
                    "session_id": session_id,
                    "messages": [m.model_dump(mode="json") for m in messages],
                    "total": len(messages),
                }
            except Exception as exc:
                logger.warning("[get_messages] Communication service error for session=%s: %s", session_id, exc)
        return {"session_id": session_id, "messages": [], "total": 0}

    # --- Auto-run endpoint for running N full turns ---

    class AutoRunResponse(BaseModel):
        success: bool
        session_id: str
        turns_completed: int
        final_turn_number: int
        final_phase: ScenePhase
        total_events: int
        events: list[dict] = Field(default_factory=list)
        state: GameState
        errors: list[str] = Field(default_factory=list)

    @router.post("/sessions/{session_id}/auto-run", response_model=AutoRunResponse)
    async def auto_run_session(
        request: Request,
        session_id: Annotated[str, Path(description="The session identifier")],
        turns: Annotated[int, Query(ge=1, le=20, description="Number of full turns to run")] = 3,
    ) -> AutoRunResponse:
        """Run multiple full turn cycles and return accumulated events + final state."""
        sessions = request.app.state.sessions
        if session_id not in sessions:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

        turn_runner: TurnRunner = request.app.state.turn_runner
        all_events: list[dict] = []
        all_errors: list[str] = []
        turns_done = 0

        for i in range(turns):
            state = sessions[session_id]
            ctx = create_phase_context(session_id, state)

            try:
                result = await turn_runner.run_full_turn_cycle(ctx)
            except Exception as e:
                all_errors.append(f"Turn {i + 1} failed: {str(e)}")
                break

            sessions[session_id] = result.final_state
            all_events.extend(_serialize_events(result.events))
            all_errors.extend(result.errors)
            turns_done += 1

            if not result.success:
                all_errors.append(f"Turn {i + 1} reported failure")
                break

        final_state = sessions[session_id]
        return AutoRunResponse(
            success=len(all_errors) == 0,
            session_id=session_id,
            turns_completed=turns_done,
            final_turn_number=final_state.turn.turn_number,
            final_phase=final_state.scene.phase,
            total_events=len(all_events),
            events=all_events,
            state=final_state,
            errors=all_errors,
        )

    # --- SSE streaming endpoint for real-time turn execution ---

    class StreamingPublisher:
        """Event publisher that pushes events to an asyncio.Queue for SSE streaming."""

        def __init__(self, queue: asyncio.Queue, store: InMemoryEventStore) -> None:
            self._queue = queue
            self._store = store

        async def publish(self, event: object) -> None:
            await self._store.publish(event)
            if hasattr(event, "model_dump"):
                serialized = event.model_dump(mode="json")
            elif hasattr(event, "__dict__"):
                serialized = dict(event.__dict__)
            else:
                serialized = {"type": str(type(event).__name__)}
            await self._queue.put(serialized)

    class TokenForwardingAgentClient:
        """Wraps AgentRuntimeClient to stream tokens to the SSE queue."""

        def __init__(self, real_client, queue: asyncio.Queue) -> None:
            self._real = real_client
            self._queue = queue

        async def invoke_agent(self, request) -> InvokeAgentResponse:
            async def on_token(actor_id: str, token: str):
                await self._queue.put({
                    "event_type": "agent.token",
                    "payload": {"actor_id": actor_id, "token": token},
                })

            return await self._real.invoke_agent_streaming(request, on_token=on_token)

        async def health_check(self) -> bool:
            return await self._real.health_check()

    class TokenForwardingClients:
        """Wraps ServiceClients to use streaming agent invocation."""

        def __init__(self, real_clients: ServiceClients, queue: asyncio.Queue) -> None:
            self.agent_runtime = TokenForwardingAgentClient(real_clients.agent_runtime, queue)
            self.game_engine = real_clients.game_engine
            self.communication = real_clients.communication
            self.http_client = real_clients.http_client

    @router.get("/sessions/{session_id}/stream-turn")
    async def stream_turn(
        request: Request,
        session_id: Annotated[str, Path(description="The session identifier")],
    ):
        """Run a full turn and stream events via SSE as they happen."""
        sessions = request.app.state.sessions
        if session_id not in sessions:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

        state = sessions[session_id]
        event_queue: asyncio.Queue = asyncio.Queue()
        es: InMemoryEventStore = request.app.state.event_store
        streaming_publisher = StreamingPublisher(event_queue, es)

        streaming_clients = TokenForwardingClients(request.app.state.service_clients, event_queue)
        streaming_runner = create_turn_runner(
            coordinator=request.app.state.coordinator if hasattr(request.app.state, 'coordinator') else None,
            clients=streaming_clients,
            publisher=streaming_publisher,
            human_action_store=request.app.state.human_action_store,
            override_store=request.app.state.override_store,
            last_resolution_store=request.app.state.last_resolution_store,
            trace_logger=request.app.state.trace_logger,
        )

        turn_task_complete = asyncio.Event()
        turn_result_holder: list = []

        async def run_turn_in_background():
            try:
                ctx = create_phase_context(session_id, state)
                result = await streaming_runner.run_full_turn_cycle(ctx)
                sessions[session_id] = result.final_state
                turn_result_holder.append(result)
            except Exception as e:
                await event_queue.put({"event_type": "error", "payload": {"message": str(e)}})
            finally:
                turn_task_complete.set()
                await event_queue.put(None)

        async def event_generator():
            task = asyncio.create_task(run_turn_in_background())

            yield f"data: {json_module.dumps({'event_type': 'turn.started', 'payload': {'turn_number': state.turn.turn_number, 'active_actor': state.scene.active_actor_id}})}\n\n"

            while True:
                try:
                    event = await asyncio.wait_for(event_queue.get(), timeout=180.0)
                except asyncio.TimeoutError:
                    yield f"data: {json_module.dumps({'event_type': 'timeout', 'payload': {}})}\n\n"
                    break

                if event is None:
                    break

                try:
                    yield f"data: {json_module.dumps(event, default=str)}\n\n"
                except Exception:
                    yield f"data: {json_module.dumps({'event_type': 'serialize_error'})}\n\n"

            if turn_result_holder:
                result = turn_result_holder[0]
                final = {
                    "event_type": "turn.complete",
                    "payload": {
                        "success": result.success,
                        "turn_number": result.final_state.turn.turn_number,
                        "phase": result.final_state.scene.phase,
                        "events_count": len(result.events),
                        "state": result.final_state.model_dump(mode="json"),
                        "errors": result.errors,
                    }
                }
                yield f"data: {json_module.dumps(final, default=str)}\n\n"

            await task

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @router.get("/sessions/{session_id}/stream-play")
    async def stream_play(
        request: Request,
        session_id: Annotated[str, Path(description="The session identifier")],
        max_turns: Annotated[int, Query(ge=1, le=50)] = 20,
    ):
        """Run turns continuously via SSE, streaming events in real-time until max_turns or client disconnects."""
        sessions = request.app.state.sessions
        if session_id not in sessions:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

        es: InMemoryEventStore = request.app.state.event_store
        base_runner: TurnRunner = request.app.state.turn_runner

        async def play_generator():
            turns_played = 0
            try:
                yield f"data: {json_module.dumps({'event_type': 'play.started', 'payload': {'max_turns': max_turns}})}\n\n"

                for turn_idx in range(max_turns):
                    state = sessions.get(session_id)
                    if state is None:
                        break

                    event_queue: asyncio.Queue = asyncio.Queue()
                    streaming_pub = StreamingPublisher(event_queue, es)
                    streaming_clients = TokenForwardingClients(request.app.state.service_clients, event_queue)

                    runner = create_turn_runner(
                        coordinator=request.app.state.coordinator if hasattr(request.app.state, 'coordinator') else None,
                        clients=streaming_clients,
                        publisher=streaming_pub,
                        human_action_store=request.app.state.human_action_store,
                        override_store=request.app.state.override_store,
                        last_resolution_store=request.app.state.last_resolution_store,
                        trace_logger=request.app.state.trace_logger,
                    )

                    turn_done = asyncio.Event()
                    result_holder: list = []

                    async def run_one_turn():
                        try:
                            ctx = create_phase_context(session_id, state)
                            result = await runner.run_full_turn_cycle(ctx)
                            sessions[session_id] = result.final_state
                            result_holder.append(result)
                        except Exception as e:
                            logger.error("[stream_play] run_one_turn error: %s", e, exc_info=True)
                            await event_queue.put({"event_type": "error", "payload": {"message": str(e)}})
                        finally:
                            turn_done.set()
                            await event_queue.put(None)

                    task = asyncio.create_task(run_one_turn())

                    while True:
                        try:
                            evt = await asyncio.wait_for(event_queue.get(), timeout=180.0)
                        except asyncio.TimeoutError:
                            yield f"data: {json_module.dumps({'event_type': 'timeout'})}\n\n"
                            await task
                            return

                        if evt is None:
                            break

                        try:
                            yield f"data: {json_module.dumps(evt, default=str)}\n\n"
                        except Exception as exc:
                            logger.error("[stream_play] Failed to serialize event: %s | event=%s", exc, type(evt).__name__)
                            yield f"data: {json_module.dumps({'event_type': 'serialize_error'})}\n\n"

                    await task

                    if result_holder:
                        r = result_holder[0]
                        try:
                            state_json = r.final_state.model_dump(mode='json')
                            yield f"data: {json_module.dumps({'event_type': 'turn.complete', 'payload': {'turn_number': r.final_state.turn.turn_number, 'success': r.success, 'state': state_json}}, default=str)}\n\n"
                        except Exception as exc:
                            logger.error("[stream_play] Failed to serialize turn.complete: %s", exc, exc_info=True)
                            yield f"data: {json_module.dumps({'event_type': 'turn.complete', 'payload': {'turn_number': r.final_state.turn.turn_number, 'success': r.success}}, default=str)}\n\n"

                    turns_played = turn_idx + 1
                    await asyncio.sleep(0.5)

                yield f"data: {json_module.dumps({'event_type': 'play.ended', 'payload': {'turns_played': turns_played}})}\n\n"
            except Exception as exc:
                logger.error("[stream_play] Generator exception: %s", exc, exc_info=True)
                yield f"data: {json_module.dumps({'event_type': 'error', 'payload': {'message': str(exc)}})}\n\n"

        return StreamingResponse(
            play_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )

    app.include_router(router, tags=["orchestrator"])

    return app


def main() -> None:
    settings = ServiceSettings.for_service("orchestrator", 8001)
    app = create_app(settings)
    uvicorn.run(app, host="0.0.0.0", port=settings.port)


if __name__ == "__main__":
    main()
