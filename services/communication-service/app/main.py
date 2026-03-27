from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Annotated, AsyncGenerator, Literal
import uuid

import uvicorn
from fastapi import APIRouter, FastAPI, HTTPException, Path, Query, Request, status
from pydantic import BaseModel, Field

from shared_config.connections import (
    check_postgres_health,
    check_rabbitmq_health,
    check_redis_health,
)
from shared_config.settings import ServiceSettings
from shared_schemas.enums import MessageChannel, ScenePhase, Visibility, ActorRole
from shared_schemas.messages import TableMessage
from shared_schemas.state import (
    CharacterState,
    GameState,
    NpcState,
    SceneState,
    TurnState,
    VisibilityScope,
)

from .budgets import BudgetConfig, get_budget_enforcer
from .message_service import (
    CreateMessageRequest,
    InMemoryMessageStore,
    MessageService,
    get_message_service,
)
from .visibility import get_visibility_rules


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings: ServiceSettings = app.state.settings
    print(f"Starting {settings.service_name} on port {settings.port}")

    app.state.message_store = InMemoryMessageStore()
    app.state.message_service = get_message_service(
        store=app.state.message_store,
        budget_enforcer=get_budget_enforcer(),
        visibility_rules=get_visibility_rules(),
    )
    app.state.sessions: dict[str, GameState] = {}

    yield

    print(f"Shutting down {settings.service_name}")


def create_app(settings: ServiceSettings | None = None) -> FastAPI:
    if settings is None:
        settings = ServiceSettings.for_service("communication-service", 8004)

    app = FastAPI(
        title="DungeonCore Communication Service",
        description="Message creation, retrieval, and visibility management",
        version="0.1.0",
        lifespan=lifespan,
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

    class CreateMessageRequestBody(BaseModel):
        session_id: str
        scene_id: str
        turn_number: int = Field(ge=0)
        phase: ScenePhase
        channel: MessageChannel
        sender_id: str
        text: str
        recipient_ids: list[str] = Field(default_factory=list)
        visibility: Visibility | None = None

    class CreateMessageResponse(BaseModel):
        success: bool
        message: TableMessage | None = None
        error: str | None = None

    @router.post("/messages", response_model=CreateMessageResponse, status_code=status.HTTP_201_CREATED)
    async def create_message(request: Request, body: CreateMessageRequestBody) -> CreateMessageResponse:
        service: MessageService = request.app.state.message_service

        req = CreateMessageRequest(
            session_id=body.session_id,
            scene_id=body.scene_id,
            turn_number=body.turn_number,
            phase=body.phase,
            channel=body.channel,
            sender_id=body.sender_id,
            text=body.text,
            recipient_ids=body.recipient_ids,
            visibility=body.visibility,
        )

        result = service.create_message(req)

        if not result.success:
            return CreateMessageResponse(
                success=False,
                error=result.error,
            )

        return CreateMessageResponse(
            success=True,
            message=result.message,
        )

    class GetMessagesResponse(BaseModel):
        messages: list[TableMessage]
        total: int

    @router.get("/sessions/{session_id}/messages", response_model=GetMessagesResponse)
    async def get_messages(
        request: Request,
        session_id: Annotated[str, Path(description="The session identifier")],
        viewer_id: Annotated[str | None, Query(description="Filter by visibility for this viewer")] = None,
        turn_number: Annotated[int | None, Query(description="Filter by turn number", ge=0)] = None,
    ) -> GetMessagesResponse:
        service: MessageService = request.app.state.message_service
        sessions: dict[str, GameState] = request.app.state.sessions

        if viewer_id and session_id in sessions:
            state = sessions[session_id]
            messages = service.get_visible_messages(
                session_id=session_id,
                viewer_id=viewer_id,
                state=state,
                turn_number=turn_number,
            )
        else:
            if turn_number is not None:
                messages = service.store.get_by_session_and_turn(session_id, turn_number)
            else:
                messages = service.get_all_messages(session_id)

        return GetMessagesResponse(
            messages=messages,
            total=len(messages),
        )

    class BudgetResponse(BaseModel):
        total_remaining: int
        actor_remaining: int
        channel_remaining: int

    @router.get("/sessions/{session_id}/budget", response_model=BudgetResponse)
    async def get_budget(
        request: Request,
        session_id: Annotated[str, Path(description="The session identifier")],
        turn_number: Annotated[int, Query(description="The turn number", ge=0)],
        sender_id: Annotated[str, Query(description="The sender actor ID")],
        channel: Annotated[MessageChannel, Query(description="The message channel")],
    ) -> BudgetResponse:
        service: MessageService = request.app.state.message_service

        budget = service.get_remaining_budget(
            session_id=session_id,
            turn_number=turn_number,
            sender_id=sender_id,
            channel=channel,
        )

        return BudgetResponse(**budget)

    class RegisterSessionRequest(BaseModel):
        state: GameState

    class RegisterSessionResponse(BaseModel):
        session_id: str
        registered: bool

    @router.post("/sessions/{session_id}/register", response_model=RegisterSessionResponse)
    async def register_session(
        request: Request,
        session_id: Annotated[str, Path(description="The session identifier")],
        body: RegisterSessionRequest,
    ) -> RegisterSessionResponse:
        sessions: dict[str, GameState] = request.app.state.sessions
        sessions[session_id] = body.state

        return RegisterSessionResponse(
            session_id=session_id,
            registered=True,
        )

    app.include_router(router, tags=["communication"])

    return app


def main() -> None:
    settings = ServiceSettings.for_service("communication-service", 8004)
    app = create_app(settings)
    uvicorn.run(app, host="0.0.0.0", port=settings.port)


if __name__ == "__main__":
    main()
