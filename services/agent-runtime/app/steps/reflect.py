"""Reflect step: Critic/validation of the proposed action.

A lightweight critic evaluates the proposed action for tactical quality,
rule compliance, target validity, and repetitive behavior. If the critic
flags issues and the iteration budget allows, the pipeline loops back to decide.
"""
from __future__ import annotations

import json
from collections import Counter

from ..adapters.base import ModelRequest
from ..pipeline import PipelineContext


class ReflectStep:
    """Evaluates the proposed turn and optionally triggers a re-decision."""

    @property
    def name(self) -> str:
        return "reflect"

    async def execute(self, ctx: PipelineContext) -> PipelineContext:
        if ctx.proposed_turn is None:
            return ctx

        if ctx.reflection_iterations >= ctx.max_reflection_iterations:
            return ctx

        issues = self._check_structural_issues(ctx)
        if issues:
            ctx.reflection_feedback = "Structural issues found:\n" + "\n".join(f"- {i}" for i in issues)
            ctx.proposed_turn = None
            ctx.reflection_iterations += 1

            step_trace = ctx.trace.steps[-1] if ctx.trace.steps else None
            if step_trace and step_trace.step_name == self.name:
                step_trace.reflection_verdict = "fail_structural"
                step_trace.metadata["issues"] = issues

            return ctx

        # Check for repetitive behavior before LLM critique
        repetition_issues = self._check_repetitive_behavior(ctx)
        if repetition_issues:
            ctx.reflection_feedback = "Repetitive behavior detected:\n" + "\n".join(f"- {i}" for i in repetition_issues)
            ctx.proposed_turn = None
            ctx.reflection_iterations += 1

            step_trace = ctx.trace.steps[-1] if ctx.trace.steps else None
            if step_trace and step_trace.step_name == self.name:
                step_trace.reflection_verdict = "fail_repetitive"
                step_trace.metadata["issues"] = repetition_issues

            return ctx

        verdict = await self._llm_critique(ctx)

        step_trace = ctx.trace.steps[-1] if ctx.trace.steps else None
        if step_trace and step_trace.step_name == self.name:
            step_trace.reflection_verdict = verdict.get("verdict", "unknown")

        if verdict.get("verdict") == "reject" and ctx.reflection_iterations < ctx.max_reflection_iterations:
            ctx.reflection_feedback = verdict.get("feedback", "The proposed action needs improvement.")
            ctx.proposed_turn = None
            ctx.reflection_iterations += 1
        else:
            ctx.reflection_feedback = ""

        return ctx

    def _check_repetitive_behavior(self, ctx: PipelineContext) -> list[str]:
        """Check if the proposed action is repetitively redundant."""
        issues: list[str] = []
        turn = ctx.proposed_turn
        if turn is None or turn.action is None:
            return issues

        action = turn.action
        action_type = str(action.type) if hasattr(action, "type") else ""
        target_id = getattr(action, "target_id", None) or getattr(action, "location_id", None)

        if not ctx.recent_actions:
            return issues

        # Count how many times we've done this exact action on this target
        same_action_count = sum(
            1 for ra in ctx.recent_actions
            if ra.action_type == action_type and ra.target_id == target_id
        )

        # Reject if inspecting the same target 3+ times
        if action_type == "inspect" and target_id and same_action_count >= 2:
            issues.append(
                f"You have already inspected '{target_id}' {same_action_count} times. "
                f"Try 'interact' to pick up items, 'move' to explore, or 'attack' an enemy instead."
            )

        # Reject excessive defending without threats
        if action_type == "defend":
            defend_count = sum(1 for ra in ctx.recent_actions if ra.action_type == "defend")
            if defend_count >= 3:
                # Check if there are actually hostile enemies nearby
                has_nearby_threat = any(
                    npc.disposition == "hostile" and npc.alive
                    for npc in ctx.state.npcs.values()
                )
                if not has_nearby_threat:
                    issues.append(
                        f"You have defended {defend_count} times with no immediate threat. "
                        f"Move to explore the map or interact with objects."
                    )

        return issues

    def _check_structural_issues(self, ctx: PipelineContext) -> list[str]:
        issues: list[str] = []
        turn = ctx.proposed_turn
        if turn is None:
            return ["No turn proposed"]

        if turn.action:
            action = turn.action
            action_type = str(action.type) if hasattr(action, "type") else ""

            # For attack actions, validate target exists and is alive
            if action_type in ("attack", "move_and_attack"):
                if hasattr(action, "target_id") and action.target_id:
                    all_ids = set(ctx.state.characters.keys()) | set(ctx.state.npcs.keys())
                    if action.target_id not in all_ids:
                        issues.append(f"Target '{action.target_id}' does not exist in visible entities")

                    target_char = ctx.state.characters.get(action.target_id)
                    target_npc = ctx.state.npcs.get(action.target_id)
                    target = target_char or target_npc
                    if target and not target.alive:
                        issues.append(f"Target '{action.target_id}' is dead")

            # For interact actions, we allow more flexible target validation
            # (objects may not be in characters/npcs lists)

            # For inspect actions, reject attempts to inspect system/meta concepts
            if action_type == "inspect":
                target = getattr(action, "target_id", None) or getattr(action, "location_id", None)
                if target:
                    target_lower = target.lower().replace("_", " ").replace("-", " ")
                    system_concepts = {
                        "story seed", "story genre", "story themes", "story difficulty",
                        "story random seed", "map complexity", "random seed", "difficulty",
                        "system", "config", "configuration", "flags", "state", "metadata",
                    }
                    if any(concept in target_lower for concept in system_concepts):
                        issues.append(
                            f"Cannot inspect '{target}' - this is a system concept, not a game object. "
                            f"Try inspecting physical objects like altars, chests, doors, or locations."
                        )

            if turn.action.type not in [str(a) for a in ctx.allowed_actions]:
                if ctx.allowed_actions:
                    issues.append(f"Action type '{turn.action.type}' not in allowed actions: {ctx.allowed_actions}")

        return issues

    async def _llm_critique(self, ctx: PipelineContext) -> dict:
        turn = ctx.proposed_turn
        if turn is None:
            return {"verdict": "reject", "feedback": "No turn to evaluate"}

        turn_summary = []
        if turn.thought:
            turn_summary.append(f"Thought: {turn.thought}")
        if turn.speech:
            turn_summary.append(f"Speech: {turn.speech}")
        if turn.action:
            turn_summary.append(f"Action: {turn.action.type}")
            if hasattr(turn.action, "target_id") and turn.action.target_id:
                turn_summary.append(f"Target: {turn.action.target_id}")

        prompt = f"""You are a tactical advisor reviewing a D&D character's proposed action.

Situation: {ctx.perception or ctx.agent_context.scene_summary}

Proposed turn:
{chr(10).join(turn_summary)}

Evaluate:
1. Is the action tactically reasonable given the situation?
2. Does the target make sense?
3. Is there an obvious better choice being missed?

Respond with JSON:
{{"verdict": "accept" or "reject", "feedback": "Brief explanation"}}

Only reject if the action is clearly bad (attacking an ally, defending when everyone is safe, ignoring a critical threat). Accept reasonable choices even if not optimal."""

        request = ModelRequest(
            system_prompt="You are a concise tactical critic for a D&D game. Respond only with the requested JSON.",
            user_prompt=prompt,
            temperature=0.1,
            max_tokens=4096,
            response_format={"type": "json_object"},
        )

        response = await ctx.adapter.generate(request)

        step_trace = ctx.trace.steps[-1] if ctx.trace.steps else None
        if step_trace and step_trace.step_name == self.name:
            step_trace.model_calls += 1
            step_trace.tokens_used += response.tokens_used

        if not response.success:
            return {"verdict": "accept", "feedback": "Critic unavailable; accepting."}

        try:
            result = json.loads(response.raw_text.strip())
            return result
        except (json.JSONDecodeError, KeyError):
            return {"verdict": "accept", "feedback": "Could not parse critic response; accepting."}
