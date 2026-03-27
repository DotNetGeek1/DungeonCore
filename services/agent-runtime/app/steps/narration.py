"""Narration pipeline steps: Summarize, Draft, and Consistency Check.

The DM narration pipeline is a three-step chain:
1. Summarize the mechanical resolution into structured bullet points
2. Draft dramatic narration from the summary
3. Self-check that the narration doesn't contradict the mechanical results
"""

import json
import logging

from ..adapters.base import ModelRequest
from ..pipeline import PipelineContext
from ..validation import OutputValidator

logger = logging.getLogger(__name__)


class SummarizeResolutionStep:
    """Extracts a structured mechanical summary from the resolution data."""

    @property
    def name(self) -> str:
        return "summarize_resolution"

    async def execute(self, ctx: PipelineContext) -> PipelineContext:
        if not ctx.resolution_summary:
            ctx.resolution_summary = ctx.agent_context.scene_summary
        ctx.extra["mechanical_facts"] = ctx.resolution_summary
        return ctx


class DraftNarrationStep:
    """Generates dramatic narration from the mechanical resolution summary."""

    def __init__(self, validator: OutputValidator | None = None) -> None:
        self._validator = validator or OutputValidator()

    @property
    def name(self) -> str:
        return "draft_narration"

    async def execute(self, ctx: PipelineContext) -> PipelineContext:
        mechanical_facts = ctx.extra.get("mechanical_facts", ctx.resolution_summary)

        prompt = f"""RESOLUTION TO NARRATE:
{mechanical_facts}

Describe what happened dramatically. Rules:
1. Do NOT add any effects or outcomes beyond what's described above
2. Do NOT contradict the mechanical results
3. Include sensory details (sounds, sights, motion)
4. Keep it punchy: 2-4 sentences
5. Give NPCs personality in their reactions

Respond with JSON:
{{
  "speech": "Your narration text here",
  "thought": "Optional private notes about pacing or upcoming events"
}}"""

        request = ModelRequest(
            system_prompt=ctx.system_prompt,
            user_prompt=prompt,
            temperature=ctx.temperature,
            max_tokens=4096,
            response_format={"type": "json_object"},
        )

        if ctx.on_token:
            response = await ctx.adapter.generate_streaming(request, on_token=ctx.on_token)
        else:
            response = await ctx.adapter.generate(request)

        step_trace = ctx.trace.steps[-1] if ctx.trace.steps else None
        if step_trace and step_trace.step_name == self.name:
            step_trace.model_calls += 1
            step_trace.tokens_used += response.tokens_used

        if not response.success:
            logger.error("[draft_narration] LLM error for actor=%s: %s", ctx.actor_id, response.error)
            return ctx

        raw = response.raw_text.strip()
        ctx.extra["narration_raw"] = raw[:500]

        result = self._validator.validate_player_turn(raw)
        if result.valid and result.parsed:
            ctx.proposed_turn = result.parsed
            ctx.extra["draft_narration"] = result.parsed.speech or ""
        else:
            logger.warning("[draft_narration] Validation failed for actor=%s errors=%s raw=%.300s", ctx.actor_id, result.errors, raw)
            extracted = self._validator.extract_json_from_text(raw)
            if extracted:
                result2 = self._validator.validate_player_turn(extracted)
                if result2.valid and result2.parsed:
                    ctx.proposed_turn = result2.parsed
                    ctx.extra["draft_narration"] = result2.parsed.speech or ""
                    logger.info("[draft_narration] Recovered via extraction for actor=%s", ctx.actor_id)

        return ctx


class NarrationConsistencyCheckStep:
    """Verifies the drafted narration doesn't contradict the mechanical facts."""

    @property
    def name(self) -> str:
        return "narration_consistency_check"

    async def execute(self, ctx: PipelineContext) -> PipelineContext:
        draft = ctx.extra.get("draft_narration", "")
        facts = ctx.extra.get("mechanical_facts", "")

        if not draft or not facts:
            return ctx

        prompt = f"""Check this D&D narration for consistency with the mechanical results.

MECHANICAL FACTS:
{facts}

NARRATION DRAFT:
{draft}

Does the narration contradict any mechanical fact? For example:
- Says an attack hit when it missed
- Mentions damage that didn't happen
- Describes effects not in the resolution

Respond with JSON:
{{"consistent": true/false, "issues": ["list of issues if any"]}}"""

        request = ModelRequest(
            system_prompt="You are a strict fact-checker for D&D narration. Respond only with the requested JSON.",
            user_prompt=prompt,
            temperature=0.0,
            max_tokens=4096,
            response_format={"type": "json_object"},
        )

        response = await ctx.adapter.generate(request)

        step_trace = ctx.trace.steps[-1] if ctx.trace.steps else None
        if step_trace and step_trace.step_name == self.name:
            step_trace.model_calls += 1
            step_trace.tokens_used += response.tokens_used

        if not response.success:
            logger.warning("[narration_consistency] LLM error: %s", response.error)
            return ctx

        raw = response.raw_text.strip()
        if not raw:
            logger.warning(
                "[narration_consistency] LLM returned empty response (finish_reason=%s, tokens=%d)",
                response.finish_reason, response.tokens_used,
            )
            return ctx

        try:
            check = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("[narration_consistency] Failed to parse response as JSON: %.200s", raw)
            return ctx

        if step_trace:
            step_trace.reflection_verdict = "consistent" if check.get("consistent", True) else "inconsistent"
            step_trace.metadata["consistency_issues"] = check.get("issues", [])

        if not check.get("consistent", True) and ctx.proposed_turn and ctx.proposed_turn.speech:
            issues_str = "; ".join(check.get("issues", []))
            ctx.extra["consistency_issues"] = issues_str
            logger.warning("[narration_consistency] Inconsistency detected: %s", issues_str)

        return ctx
