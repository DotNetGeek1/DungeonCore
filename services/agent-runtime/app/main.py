import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Annotated, AsyncGenerator, Literal

import uvicorn
from fastapi import APIRouter, FastAPI, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

from shared_config.connections import (
    check_postgres_health,
    check_rabbitmq_health,
    check_redis_health,
)
from shared_config.settings import ServiceSettings
from shared_schemas.actions import PlayerTurn
from shared_schemas.context import AgentContext
from shared_schemas.enums import ActionType, ActorRole
from shared_schemas.memory import MemoryEntry
from shared_schemas.state import GameState

from game_rules import RulesLoader

from .adapters import ModelAdapter, ModelRequest
from .adapters.factory import create_adapter
from .context_builder import ContextBuilder, get_context_builder
from .memory_retrieval import InMemoryMemoryStore, MemoryRetriever, get_memory_retriever
from .pipeline import PipelineContext, PipelineTrace
from .pipelines import (
    build_action_pipeline,
    build_discussion_pipeline,
    build_narration_pipeline,
    build_reaction_pipeline,
)
from .retry import InvocationTrace, RetryConfig, RetryHandler, get_retry_handler
from .tools.registry import create_default_registry, create_dm_registry
from .trace_store import PipelineTraceStore
from .validation import OutputValidator, get_output_validator


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    settings: ServiceSettings = app.state.settings
    print(f"Starting {settings.service_name} on port {settings.port}")
    print(f"Model provider: {settings.model_provider}")

    adapter = create_adapter(settings)
    app.state.adapter = adapter
    print(f"Adapter created: {adapter.provider_name}")

    rules = RulesLoader()
    app.state.rules = rules

    app.state.validator = get_output_validator()
    app.state.context_builder = get_context_builder(rules=rules)
    app.state.memory_store = InMemoryMemoryStore()
    app.state.memory_retriever = get_memory_retriever(store=app.state.memory_store)
    app.state.retry_handler = get_retry_handler(
        adapter=adapter,
        validator=app.state.validator,
        config=RetryConfig(max_retries=2),
    )
    app.state.pipeline_trace_store = PipelineTraceStore()

    yield

    await adapter.close()
    print(f"Shutting down {settings.service_name}")


def create_app(settings: ServiceSettings | None = None) -> FastAPI:
    if settings is None:
        settings = ServiceSettings.for_service("agent-runtime", 8002)

    app = FastAPI(
        title="DungeonCore Agent Runtime",
        description="LLM agent invocation and context management",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.settings = settings

    router = APIRouter()

    class DependencyStatus(BaseModel):
        postgres: bool
        redis: bool
        rabbitmq: bool
        model_provider_healthy: bool = False

    class HealthResponse(BaseModel):
        service: str
        status: Literal["ok", "degraded"]
        port: int
        dependencies: DependencyStatus
        model_provider: str
        model_provider_name: str

    @router.get("/health", response_model=HealthResponse)
    async def health_check(request: Request) -> HealthResponse:
        settings: ServiceSettings = request.app.state.settings
        adapter: ModelAdapter = request.app.state.adapter

        model_provider_healthy = await adapter.health_check()

        deps = DependencyStatus(
            postgres=check_postgres_health(settings),
            redis=check_redis_health(settings),
            rabbitmq=check_rabbitmq_health(settings),
            model_provider_healthy=model_provider_healthy,
        )
        all_healthy = deps.postgres and deps.redis and deps.rabbitmq
        return HealthResponse(
            service=settings.service_name,
            status="ok" if all_healthy else "degraded",
            port=settings.port,
            dependencies=deps,
            model_provider=settings.model_provider,
            model_provider_name=adapter.provider_name,
        )

    PIPELINE_MODES = {"discussion", "action_commit", "narration", "reaction"}

    class RecentActionRecord(BaseModel):
        action_type: str
        target_id: str | None = None
        turn_number: int

    class InvokeAgentRequest(BaseModel):
        session_id: str
        agent_id: str
        actor_id: str
        actor_name: str
        role: ActorRole
        goals: list[str] = Field(default_factory=list)
        state: GameState
        system_prompt: str | None = None
        temperature: float = 0.4
        invocation_mode: str | None = None
        resolution_summary: str | None = None
        messages: list[dict] = Field(default_factory=list)
        recent_actions: list[RecentActionRecord] = Field(default_factory=list)

    class InvokeAgentResponse(BaseModel):
        success: bool
        turn: PlayerTurn | None = None
        trace: dict | None = None
        error: str | None = None
        state: GameState | None = None  # Updated state after tool execution

    def _build_default_system_prompt(role: ActorRole, name: str, goals: list[str]) -> str:
        base = f"You are {name}, a {role} character in a D&D game."

        if goals:
            base += f"\n\nYour goals:\n" + "\n".join(f"- {g}" for g in goals)

        base += """

You must respond with a valid JSON object containing your turn. The format is:
{
  "thought": "Your private reasoning (optional)",
  "speech": "What you say in character (optional)",
  "table_talk": "Tactical coordination with other players (optional)",
  "action": {
    "type": "attack|move|defend|inspect|cast_spell_basic|move_and_attack",
    ... action-specific fields ...
  }
}

You must provide at least speech, table_talk, or an action.
"""
        return base

    def _build_user_prompt(ctx: AgentContext) -> str:
        parts = [
            "Current situation:",
            ctx.scene_summary,
            "",
            "Your character:",
            f"- Name: {ctx.identity.name}",
            f"- Role: {ctx.identity.role}",
            "",
        ]

        if ctx.recent_messages:
            parts.append("Recent messages:")
            for msg in ctx.recent_messages[-5:]:
                parts.append(f"- [{msg.channel}] {msg.sender_id}: {msg.text}")
            parts.append("")

        if ctx.memories:
            parts.append("Relevant memories:")
            for mem in ctx.memories[:3]:
                parts.append(f"- {mem.text}")
            parts.append("")

        parts.append("Available actions: " + ", ".join(str(a) for a in ctx.allowed_actions))
        parts.append("")
        parts.append("What do you do?")

        return "\n".join(parts)

    def _serialize_pipeline_trace(trace: PipelineTrace) -> dict:
        return {
            "agent_id": trace.agent_id,
            "invocation_mode": trace.invocation_mode,
            "provider": trace.provider,
            "model": trace.model,
            "total_latency_ms": trace.total_latency_ms,
            "total_tokens": trace.total_tokens,
            "total_model_calls": trace.total_model_calls,
            "memories_retrieved": trace.memories_retrieved,
            "final_validation": trace.final_validation,
            "error": trace.error,
            "steps": [
                {
                    "step": s.step_name,
                    "latency_ms": s.latency_ms,
                    "model_calls": s.model_calls,
                    "tokens_used": s.tokens_used,
                    "tool_calls": [
                        {"tool": tc.tool_name, "args": tc.arguments, "result_preview": tc.result[:200]}
                        for tc in s.tool_calls
                    ],
                    "reflection_verdict": s.reflection_verdict,
                    "error": s.error,
                }
                for s in trace.steps
            ],
        }

    @router.post("/invoke", response_model=InvokeAgentResponse)
    async def invoke_agent(request: Request, body: InvokeAgentRequest) -> InvokeAgentResponse:
        from shared_schemas.messages import TableMessage

        context_builder: ContextBuilder = request.app.state.context_builder
        memory_retriever: MemoryRetriever = request.app.state.memory_retriever
        adapter: ModelAdapter = request.app.state.adapter
        validator: OutputValidator = request.app.state.validator
        rules = request.app.state.rules

        memories = memory_retriever.retrieve(
            session_id=body.session_id,
            actor_id=body.actor_id,
            current_turn=body.state.turn.turn_number,
        )

        # Parse messages from the request
        parsed_messages: list[TableMessage] = []
        for msg_dict in body.messages:
            try:
                parsed_messages.append(TableMessage.model_validate(msg_dict))
            except Exception:
                pass

        agent_ctx = context_builder.build_context(
            session_id=body.session_id,
            agent_id=body.agent_id,
            actor_id=body.actor_id,
            actor_name=body.actor_name,
            role=body.role,
            goals=body.goals,
            state=body.state,
            memories=memories,
            messages=parsed_messages,
        )

        system_prompt = body.system_prompt or _build_default_system_prompt(
            body.role, body.actor_name, body.goals
        )
        # Use structured prompt which includes the map section for spatial awareness
        user_prompt = context_builder.build_structured_prompt(
            agent_ctx,
            actor_name=body.actor_name,
            role=body.role,
            goals=body.goals,
        )

        mode = body.invocation_mode
        if mode and mode in PIPELINE_MODES:
            if body.role == ActorRole.DM:
                tool_registry = create_dm_registry(
                    rules=rules, state=body.state, recent_messages=agent_ctx.recent_messages,
                )
            else:
                tool_registry = create_default_registry(
                    rules=rules, state=body.state, recent_messages=agent_ctx.recent_messages,
                )

            # Convert recent action records to pipeline format
            from .pipeline import RecentAction
            recent_actions_for_pipeline = [
                RecentAction(
                    action_type=ra.action_type,
                    target_id=ra.target_id,
                    turn_number=ra.turn_number,
                )
                for ra in body.recent_actions
            ]

            pipeline_ctx = PipelineContext(
                session_id=body.session_id,
                agent_id=body.agent_id,
                actor_id=body.actor_id,
                actor_name=body.actor_name,
                role=body.role,
                goals=body.goals,
                state=body.state,
                agent_context=agent_ctx,
                adapter=adapter,
                memories=memories,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=body.temperature,
                allowed_actions=list(agent_ctx.allowed_actions),
                resolution_summary=body.resolution_summary or "",
                recent_actions=recent_actions_for_pipeline,
            )

            if mode == "discussion":
                pipeline = build_discussion_pipeline(validator)
            elif mode == "action_commit":
                pipeline = build_action_pipeline(tool_registry, validator)
            elif mode == "narration":
                pipeline = build_narration_pipeline(validator)
            elif mode == "reaction":
                pipeline = build_reaction_pipeline(validator)
            else:
                pipeline = build_action_pipeline(tool_registry, validator)

            result = await pipeline.run(pipeline_ctx)

            if result.trace:
                trace_store: PipelineTraceStore = request.app.state.pipeline_trace_store
                trace_store.store(result.trace)

            # Return the potentially modified state (e.g., after map tool execution)
            has_map = body.state.dungeon_map is not None
            map_name = body.state.dungeon_map.name if has_map else "None"
            logger.info(
                "[invoke_agent] Returning state: dungeon_map=%s (name=%s) for actor=%s mode=%s",
                has_map, map_name, body.actor_id, mode,
            )
            
            response = InvokeAgentResponse(
                success=result.success,
                turn=result.turn,
                trace=_serialize_pipeline_trace(result.trace) if result.trace else None,
                error=result.error,
                state=body.state,  # State may have been modified by tools
            )
            
            # Debug: verify state is in response
            if response.state is None:
                logger.error("[invoke_agent] Response state is None even though body.state exists!")
            elif response.state.dungeon_map is None and has_map:
                logger.error("[invoke_agent] Response state lost dungeon_map during assignment!")
            
            return response

        # Legacy single-shot path (no invocation_mode specified)
        retry_handler: RetryHandler = request.app.state.retry_handler

        model_request = ModelRequest(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=body.temperature,
            response_format={"type": "json_object"},
        )

        turn, trace = await retry_handler.invoke_with_retry(
            request=model_request,
            agent_id=body.agent_id,
            context_summary=agent_ctx.scene_summary,
        )

        return InvokeAgentResponse(
            success=turn is not None,
            turn=turn,
            trace={
                "agent_id": trace.agent_id,
                "provider": trace.provider,
                "model": trace.model,
                "validation_result": trace.validation_result,
                "retries": trace.retries,
                "latency_ms": trace.latency_ms,
                "error": trace.error,
            },
            error=trace.error,
        )

    @router.post("/invoke-stream")
    async def invoke_agent_streaming(request: Request, body: InvokeAgentRequest):
        """Invoke agent with SSE token streaming."""
        from shared_schemas.messages import TableMessage

        context_builder: ContextBuilder = request.app.state.context_builder
        memory_retriever: MemoryRetriever = request.app.state.memory_retriever
        adapter: ModelAdapter = request.app.state.adapter
        validator: OutputValidator = request.app.state.validator
        rules = request.app.state.rules

        memories = memory_retriever.retrieve(
            session_id=body.session_id,
            actor_id=body.actor_id,
            current_turn=body.state.turn.turn_number,
        )

        # Parse messages from the request
        parsed_messages: list[TableMessage] = []
        for msg_dict in body.messages:
            try:
                parsed_messages.append(TableMessage.model_validate(msg_dict))
            except Exception:
                pass

        agent_ctx = context_builder.build_context(
            session_id=body.session_id,
            agent_id=body.agent_id,
            actor_id=body.actor_id,
            actor_name=body.actor_name,
            role=body.role,
            goals=body.goals,
            state=body.state,
            memories=memories,
            messages=parsed_messages,
        )

        system_prompt = body.system_prompt or _build_default_system_prompt(
            body.role, body.actor_name, body.goals
        )
        # Use structured prompt which includes the map section for spatial awareness
        user_prompt = context_builder.build_structured_prompt(
            agent_ctx,
            actor_name=body.actor_name,
            role=body.role,
            goals=body.goals,
        )

        token_queue: asyncio.Queue = asyncio.Queue()

        async def on_token(token: str):
            await token_queue.put(token)

        mode = body.invocation_mode

        async def run_pipeline():
            if mode and mode in PIPELINE_MODES:
                if body.role == ActorRole.DM:
                    tool_registry = create_dm_registry(
                        rules=rules, state=body.state, recent_messages=agent_ctx.recent_messages,
                    )
                else:
                    tool_registry = create_default_registry(
                        rules=rules, state=body.state, recent_messages=agent_ctx.recent_messages,
                    )
                # Convert recent action records to pipeline format
                from .pipeline import RecentAction
                recent_actions_for_pipeline = [
                    RecentAction(
                        action_type=ra.action_type,
                        target_id=ra.target_id,
                        turn_number=ra.turn_number,
                    )
                    for ra in body.recent_actions
                ]

                pipeline_ctx = PipelineContext(
                    session_id=body.session_id,
                    agent_id=body.agent_id,
                    actor_id=body.actor_id,
                    actor_name=body.actor_name,
                    role=body.role,
                    goals=body.goals,
                    state=body.state,
                    agent_context=agent_ctx,
                    adapter=adapter,
                    memories=memories,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    temperature=body.temperature,
                    allowed_actions=list(agent_ctx.allowed_actions),
                    resolution_summary=body.resolution_summary or "",
                    on_token=on_token,
                    recent_actions=recent_actions_for_pipeline,
                )

                if mode == "discussion":
                    pipeline = build_discussion_pipeline(validator)
                elif mode == "action_commit":
                    pipeline = build_action_pipeline(tool_registry, validator)
                elif mode == "narration":
                    pipeline = build_narration_pipeline(validator)
                elif mode == "reaction":
                    pipeline = build_reaction_pipeline(validator)
                else:
                    pipeline = build_action_pipeline(tool_registry, validator)

                return await pipeline.run(pipeline_ctx)
            else:
                retry_handler: RetryHandler = request.app.state.retry_handler
                model_request = ModelRequest(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    temperature=body.temperature,
                )
                turn, trace = await retry_handler.invoke_with_retry(
                    request=model_request,
                    agent_id=body.agent_id,
                    context_summary=agent_ctx.scene_summary,
                )
                return turn, trace

        async def sse_generator():
            pipeline_done = asyncio.Event()
            result_holder: list = []

            async def run_and_signal():
                try:
                    result = await run_pipeline()
                    result_holder.append(result)
                except Exception as e:
                    result_holder.append(e)
                finally:
                    pipeline_done.set()
                    await token_queue.put(None)

            task = asyncio.create_task(run_and_signal())

            while True:
                try:
                    token = await asyncio.wait_for(token_queue.get(), timeout=180.0)
                except asyncio.TimeoutError:
                    break
                if token is None:
                    break
                yield f"data: {json.dumps({'type': 'token', 'token': token})}\n\n"

            await task

            if result_holder:
                result = result_holder[0]
                # Include the potentially modified state in the response
                state_data = body.state.model_dump(mode="json")
                
                if isinstance(result, Exception):
                    yield f"data: {json.dumps({'type': 'error', 'error': str(result), 'state': state_data})}\n\n"
                elif hasattr(result, 'turn'):
                    pr = result
                    turn_data = pr.turn.model_dump(mode="json") if pr.turn else None
                    yield f"data: {json.dumps({'type': 'result', 'success': pr.success, 'turn': turn_data, 'error': pr.error, 'state': state_data})}\n\n"
                elif isinstance(result, tuple):
                    turn, trace = result
                    turn_data = turn.model_dump(mode="json") if turn else None
                    yield f"data: {json.dumps({'type': 'result', 'success': turn is not None, 'turn': turn_data, 'error': trace.error, 'state': state_data})}\n\n"

        return StreamingResponse(
            sse_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )

    class ValidateOutputRequest(BaseModel):
        raw_text: str

    class ValidateOutputResponse(BaseModel):
        valid: bool
        turn: PlayerTurn | None = None
        errors: list[str] = Field(default_factory=list)

    @router.post("/validate-output", response_model=ValidateOutputResponse)
    async def validate_output(request: Request, body: ValidateOutputRequest) -> ValidateOutputResponse:
        validator: OutputValidator = request.app.state.validator

        result = validator.validate_player_turn(body.raw_text)

        return ValidateOutputResponse(
            valid=result.valid,
            turn=result.parsed,
            errors=result.errors,
        )

    class BuildContextRequest(BaseModel):
        session_id: str
        agent_id: str
        actor_id: str
        actor_name: str
        role: ActorRole
        goals: list[str] = Field(default_factory=list)
        state: GameState

    class BuildContextResponse(BaseModel):
        context: AgentContext

    @router.post("/build-context", response_model=BuildContextResponse)
    async def build_context(request: Request, body: BuildContextRequest) -> BuildContextResponse:
        context_builder: ContextBuilder = request.app.state.context_builder
        memory_retriever: MemoryRetriever = request.app.state.memory_retriever

        memories = memory_retriever.retrieve(
            session_id=body.session_id,
            actor_id=body.actor_id,
            current_turn=body.state.turn.turn_number,
        )

        ctx = context_builder.build_context(
            session_id=body.session_id,
            agent_id=body.agent_id,
            actor_id=body.actor_id,
            actor_name=body.actor_name,
            role=body.role,
            goals=body.goals,
            state=body.state,
            memories=memories,
        )

        return BuildContextResponse(context=ctx)

    class GetTracesResponse(BaseModel):
        legacy_traces: list[dict] = Field(default_factory=list)
        pipeline_traces: list[dict] = Field(default_factory=list)
        total_count: int = 0

    @router.get("/traces", response_model=GetTracesResponse)
    async def get_traces(request: Request) -> GetTracesResponse:
        retry_handler: RetryHandler = request.app.state.retry_handler
        legacy = retry_handler.get_traces()

        trace_store: PipelineTraceStore = request.app.state.pipeline_trace_store
        pipeline_traces = trace_store.serialize_all()

        return GetTracesResponse(
            legacy_traces=[
                {
                    "agent_id": t.agent_id,
                    "provider": t.provider,
                    "model": t.model,
                    "prompt_hash": t.prompt_hash,
                    "context_hash": t.context_hash,
                    "validation_result": t.validation_result,
                    "retries": t.retries,
                    "latency_ms": t.latency_ms,
                    "timestamp": t.timestamp.isoformat(),
                    "error": t.error,
                }
                for t in legacy
            ],
            pipeline_traces=pipeline_traces,
            total_count=len(legacy) + len(pipeline_traces),
        )

    app.include_router(router, tags=["agent-runtime"])

    return app


def main() -> None:
    settings = ServiceSettings.for_service("agent-runtime", 8002)
    app = create_app(settings)
    uvicorn.run(app, host="0.0.0.0", port=settings.port)


if __name__ == "__main__":
    main()
