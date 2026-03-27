from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable

from shared_schemas.actions import PlayerTurn
from shared_schemas.context import AgentContext
from shared_schemas.enums import ActionType, ActorRole
from shared_schemas.memory import MemoryEntry
from shared_schemas.state import GameState

from .adapters.base import ModelAdapter, ModelRequest, ModelResponse, TokenCallback


@dataclass
class ToolCall:
    tool_name: str
    arguments: dict[str, Any]
    result: str
    latency_ms: int = 0


@dataclass
class StepTrace:
    step_name: str
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None
    latency_ms: int = 0
    model_calls: int = 0
    tokens_used: int = 0
    tool_calls: list[ToolCall] = field(default_factory=list)
    reflection_verdict: str | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PipelineTrace:
    agent_id: str
    invocation_mode: str
    provider: str = ""
    model: str = ""
    steps: list[StepTrace] = field(default_factory=list)
    total_latency_ms: int = 0
    total_tokens: int = 0
    total_model_calls: int = 0
    memories_retrieved: int = 0
    final_validation: str = "pending"
    error: str | None = None
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class RecentAction:
    """Record of a recent action taken by this agent."""
    action_type: str
    target_id: str | None
    turn_number: int


@dataclass
class PipelineContext:
    """Mutable state that flows through each pipeline step."""

    session_id: str
    agent_id: str
    actor_id: str
    actor_name: str
    role: ActorRole
    goals: list[str]
    state: GameState
    agent_context: AgentContext
    adapter: ModelAdapter
    memories: list[MemoryEntry] = field(default_factory=list)

    system_prompt: str = ""
    user_prompt: str = ""
    temperature: float = 0.4

    perception: str = ""
    reasoning: str = ""
    tool_results: dict[str, str] = field(default_factory=dict)
    proposed_turn: PlayerTurn | None = None
    reflection_feedback: str = ""
    reflection_iterations: int = 0
    max_reflection_iterations: int = 2

    messages_history: list[dict[str, str]] = field(default_factory=list)

    trace: PipelineTrace = field(default_factory=lambda: PipelineTrace(agent_id="", invocation_mode=""))
    extra: dict[str, Any] = field(default_factory=dict)

    # Set by narration pipelines
    resolution_summary: str = ""

    # Allowed actions for this agent
    allowed_actions: list[ActionType] = field(default_factory=list)

    # Optional token streaming callback
    on_token: TokenCallback | None = None

    # Recent action history for this agent (to detect repetitive loops)
    recent_actions: list[RecentAction] = field(default_factory=list)


@dataclass
class PipelineResult:
    success: bool
    turn: PlayerTurn | None = None
    trace: PipelineTrace | None = None
    error: str | None = None


@runtime_checkable
class PipelineStep(Protocol):
    @property
    def name(self) -> str: ...

    async def execute(self, ctx: PipelineContext) -> PipelineContext: ...


class AgentPipeline:
    """Executes an ordered sequence of PipelineSteps, accumulating trace data."""

    def __init__(self, steps: list[PipelineStep], name: str = "default") -> None:
        self._steps = steps
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    async def run(self, ctx: PipelineContext) -> PipelineResult:
        ctx.trace.invocation_mode = self._name
        ctx.trace.agent_id = ctx.agent_id
        ctx.trace.provider = ctx.adapter.provider_name
        start = time.perf_counter()

        for step in self._steps:
            step_trace = StepTrace(step_name=step.name)
            step_start = time.perf_counter()

            try:
                ctx = await step.execute(ctx)
            except Exception as e:
                step_trace.error = str(e)
                step_trace.latency_ms = int((time.perf_counter() - step_start) * 1000)
                step_trace.finished_at = datetime.now(timezone.utc)
                ctx.trace.steps.append(step_trace)
                ctx.trace.error = f"Step '{step.name}' failed: {e}"
                ctx.trace.total_latency_ms = int((time.perf_counter() - start) * 1000)
                return PipelineResult(
                    success=False,
                    turn=ctx.proposed_turn,
                    trace=ctx.trace,
                    error=ctx.trace.error,
                )

            step_trace.latency_ms = int((time.perf_counter() - step_start) * 1000)
            step_trace.finished_at = datetime.now(timezone.utc)
            ctx.trace.steps.append(step_trace)

        ctx.trace.total_latency_ms = int((time.perf_counter() - start) * 1000)
        ctx.trace.total_tokens = sum(s.tokens_used for s in ctx.trace.steps)
        ctx.trace.total_model_calls = sum(s.model_calls for s in ctx.trace.steps)

        return PipelineResult(
            success=ctx.proposed_turn is not None,
            turn=ctx.proposed_turn,
            trace=ctx.trace,
        )
