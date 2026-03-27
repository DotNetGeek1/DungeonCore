"""Validate output step: Final gate before returning a pipeline result.

If the pipeline produced a valid proposed_turn, marks it as valid.
If not, logs the failure — no silent fallback is injected.
"""
from __future__ import annotations

import logging

from ..pipeline import PipelineContext

logger = logging.getLogger(__name__)


class ValidateOutputStep:
    """Final validation gate — checks whether the pipeline produced a turn."""

    @property
    def name(self) -> str:
        return "validate_output"

    async def execute(self, ctx: PipelineContext) -> PipelineContext:
        if ctx.proposed_turn is not None:
            ctx.trace.final_validation = "valid"
            return ctx

        ctx.trace.final_validation = "no_output"

        errors = ctx.extra.get("compose_validation_errors") or ctx.extra.get("decide_errors") or []
        raw = ctx.extra.get("compose_raw") or ctx.extra.get("narration_raw") or ctx.extra.get("decide_raw_text") or ""

        logger.error(
            "[validate_output] Pipeline produced no turn for agent=%s actor=%s mode=%s | errors=%s | raw_preview=%.300s",
            ctx.agent_id,
            ctx.actor_id,
            ctx.trace.invocation_mode,
            errors,
            raw,
        )

        step_trace = ctx.trace.steps[-1] if ctx.trace.steps else None
        if step_trace and step_trace.step_name == self.name:
            step_trace.error = f"Pipeline produced no valid turn. Errors: {errors}"
            step_trace.metadata["raw_preview"] = raw[:300]

        return ctx
