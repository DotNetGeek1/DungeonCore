"""Pipeline factory: assembles phase-specific agent pipelines.

Each invocation mode maps to a different sequence of steps,
optimised for that phase of the game loop.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from .pipeline import AgentPipeline, PipelineStep
from .steps.compose import ComposeStep
from .steps.decide import DecideStep
from .steps.narration import (
    DraftNarrationStep,
    NarrationConsistencyCheckStep,
    SummarizeResolutionStep,
)
from .steps.perceive import PerceiveStep
from .steps.reflect import ReflectStep
from .steps.tool_query import ToolQueryStep
from .steps.validate_output import ValidateOutputStep
from .tools.registry import ToolRegistry
from .validation import OutputValidator

if TYPE_CHECKING:
    pass


class ReflectingActionPipeline(AgentPipeline):
    """Action pipeline with a reflect->retry loop.

    Runs: perceive -> tool_query -> decide -> reflect
    If reflect rejects and budget remains, loops back to decide.
    Finally validates output with fallback.
    """

    def __init__(
        self,
        tool_registry: ToolRegistry,
        validator: OutputValidator,
        max_reflection_loops: int = 2,
    ) -> None:
        self._perceive = PerceiveStep()
        self._tool_query = ToolQueryStep(tool_registry)
        self._decide = DecideStep(validator)
        self._reflect = ReflectStep()
        self._validate = ValidateOutputStep()
        self._max_loops = max_reflection_loops

        super().__init__(
            steps=[self._perceive, self._tool_query, self._decide, self._reflect, self._validate],
            name="action_commit",
        )

    async def run(self, ctx):
        from .pipeline import PipelineResult, StepTrace
        import time
        import json
        from datetime import datetime, timezone

        ctx.trace.invocation_mode = self._name
        ctx.trace.agent_id = ctx.agent_id
        ctx.trace.provider = ctx.adapter.provider_name
        start = time.perf_counter()

        for step in [self._perceive, self._tool_query]:
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
                return PipelineResult(success=False, turn=ctx.proposed_turn, trace=ctx.trace, error=ctx.trace.error)
            step_trace.latency_ms = int((time.perf_counter() - step_start) * 1000)
            step_trace.finished_at = datetime.now(timezone.utc)
            ctx.trace.steps.append(step_trace)

        # For DM map generation, skip decide/reflect - just extract speech from tool_query result
        is_dm_map_generation = ctx.actor_id == "dm" and "init_map" in ctx.tool_results
        print(f"[ReflectingActionPipeline] actor_id={ctx.actor_id}, tool_results_keys={list(ctx.tool_results.keys())}, is_dm_map_generation={is_dm_map_generation}")
        if is_dm_map_generation:
            print(f"[ReflectingActionPipeline] reasoning preview: {ctx.reasoning[:300] if ctx.reasoning else 'empty'}")
            # Try to parse the reasoning as a DM response with speech
            from shared_schemas.actions import PlayerTurn
            from .adapters.base import ModelRequest
            
            speech = None
            thought = None
            
            # First try to extract from reasoning
            try:
                raw_text = ctx.reasoning.strip()
                if raw_text.startswith("{"):
                    data = json.loads(raw_text)
                    speech = data.get("speech", "")
                    thought = data.get("thought", "")
            except (json.JSONDecodeError, Exception) as e:
                print(f"[ReflectingActionPipeline] Failed to parse DM map response: {e}")
            
            # If no speech extracted, make one more model call to get the narration
            if not speech:
                print(f"[ReflectingActionPipeline] No speech in reasoning, requesting final narration")
                finalize_prompt = """The dungeon map has been created. Now provide your opening narration for the players.

Respond with JSON:
{"speech": "Your dramatic opening narration describing the dungeon entrance", "thought": "Brief note about what you created"}"""
                
                messages = ctx.messages_history if ctx.messages_history else []
                messages.append({"role": "user", "content": finalize_prompt})
                
                request = ModelRequest(
                    system_prompt=ctx.system_prompt,
                    user_prompt="",
                    messages=messages,
                    temperature=0.7,
                    max_tokens=1024,
                    response_format={"type": "json_object"},
                )
                
                response = await ctx.adapter.generate(request)
                if response.success and response.raw_text:
                    try:
                        data = json.loads(response.raw_text)
                        speech = data.get("speech", "")
                        thought = data.get("thought", "")
                        print(f"[ReflectingActionPipeline] Got speech from finalize call: {speech[:100] if speech else 'empty'}")
                    except json.JSONDecodeError:
                        print(f"[ReflectingActionPipeline] Failed to parse finalize response")
            
            if speech:
                ctx.proposed_turn = PlayerTurn(
                    thought=thought or "Map generation complete.",
                    speech=speech,
                )
                print(f"[ReflectingActionPipeline] DM map generation complete, extracted speech")
            
            # Skip to validation
            step_trace = StepTrace(step_name=self._validate.name)
            step_start = time.perf_counter()
            try:
                ctx = await self._validate.execute(ctx)
            except Exception as e:
                step_trace.error = str(e)
            step_trace.latency_ms = int((time.perf_counter() - step_start) * 1000)
            step_trace.finished_at = datetime.now(timezone.utc)
            ctx.trace.steps.append(step_trace)
            
            ctx.trace.total_latency_ms = int((time.perf_counter() - start) * 1000)
            return PipelineResult(
                success=ctx.proposed_turn is not None,
                turn=ctx.proposed_turn,
                trace=ctx.trace,
                error=ctx.trace.error if ctx.proposed_turn is None else None,
            )

        for loop in range(self._max_loops + 1):
            for step in [self._decide, self._reflect]:
                step_trace = StepTrace(step_name=step.name)
                step_start = time.perf_counter()
                try:
                    ctx = await step.execute(ctx)
                except Exception as e:
                    step_trace.error = str(e)
                    step_trace.latency_ms = int((time.perf_counter() - step_start) * 1000)
                    step_trace.finished_at = datetime.now(timezone.utc)
                    ctx.trace.steps.append(step_trace)
                    break
                step_trace.latency_ms = int((time.perf_counter() - step_start) * 1000)
                step_trace.finished_at = datetime.now(timezone.utc)
                ctx.trace.steps.append(step_trace)

            if ctx.proposed_turn is not None:
                break

        step_trace = StepTrace(step_name=self._validate.name)
        step_start = time.perf_counter()
        try:
            ctx = await self._validate.execute(ctx)
        except Exception as e:
            step_trace.error = str(e)
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


def build_discussion_pipeline(validator: OutputValidator) -> AgentPipeline:
    return AgentPipeline(
        steps=[
            PerceiveStep(),
            ComposeStep(validator, phase="discussion"),
            ValidateOutputStep(),
        ],
        name="discussion",
    )


def build_action_pipeline(
    tool_registry: ToolRegistry,
    validator: OutputValidator,
) -> ReflectingActionPipeline:
    return ReflectingActionPipeline(tool_registry, validator)


def build_narration_pipeline(validator: OutputValidator) -> AgentPipeline:
    return AgentPipeline(
        steps=[
            SummarizeResolutionStep(),
            DraftNarrationStep(validator),
            NarrationConsistencyCheckStep(),
            ValidateOutputStep(),
        ],
        name="narration",
    )


def build_reaction_pipeline(validator: OutputValidator) -> AgentPipeline:
    return AgentPipeline(
        steps=[
            PerceiveStep(),
            ComposeStep(validator, phase="reaction"),
            ValidateOutputStep(),
        ],
        name="reaction",
    )


PIPELINE_BUILDERS = {
    "discussion": build_discussion_pipeline,
    "action_commit": build_action_pipeline,
    "narration": build_narration_pipeline,
    "reaction": build_reaction_pipeline,
}
