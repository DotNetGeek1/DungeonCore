"""Compose step: Speech/table_talk composition for discussion and reaction phases."""

import logging

from ..adapters.base import ModelRequest
from ..pipeline import PipelineContext
from ..validation import OutputValidator

logger = logging.getLogger(__name__)


class ComposeStep:
    """Generates speech/table_talk output for discussion or reaction phases."""

    def __init__(self, validator: OutputValidator | None = None, phase: str = "discussion") -> None:
        self._validator = validator or OutputValidator()
        self._phase = phase

    @property
    def name(self) -> str:
        return "compose"

    async def execute(self, ctx: PipelineContext) -> PipelineContext:
        context_parts: list[str] = []

        if ctx.perception:
            context_parts.append(f"Current situation:\n{ctx.perception}")
        else:
            context_parts.append(f"Current situation:\n{ctx.agent_context.scene_summary}")

        if ctx.agent_context.recent_messages:
            context_parts.append("Recent messages:")
            for msg in ctx.agent_context.recent_messages[-5:]:
                context_parts.append(f"  [{msg.channel}] {msg.sender_id}: {msg.text}")

        context_block = "\n\n".join(context_parts)

        if self._phase == "reaction":
            action_constraint = "You are reacting to what just happened. Keep it brief (1-2 sentences)."
        else:
            action_constraint = "You may offer a tactical suggestion, in-character comment, or both."

        prompt = f"""{context_block}

{action_constraint}

Do NOT propose an action -- only speech or table_talk is allowed in this phase.

Respond with ONLY a JSON object, no other text:
{{
  "speech": "What you say in character",
  "table_talk": "Tactical suggestion (optional)"
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

        if not response.success:
            ctx.extra["compose_error"] = response.error or "LLM call failed"
            logger.error("[compose] LLM error for actor=%s: %s", ctx.actor_id, response.error)
            return ctx

        raw = response.raw_text.strip()
        ctx.extra["compose_raw"] = raw[:500]

        result = self._validator.validate_player_turn(raw)
        if result.valid and result.parsed:
            ctx.proposed_turn = result.parsed
        else:
            ctx.extra["compose_validation_errors"] = result.errors
            logger.warning("[compose] Validation failed for actor=%s errors=%s raw=%.300s", ctx.actor_id, result.errors, raw)

            extracted = self._validator.extract_json_from_text(raw)
            if extracted:
                result2 = self._validator.validate_player_turn(extracted)
                if result2.valid and result2.parsed:
                    ctx.proposed_turn = result2.parsed
                    logger.info("[compose] Recovered via JSON extraction for actor=%s", ctx.actor_id)

        return ctx
