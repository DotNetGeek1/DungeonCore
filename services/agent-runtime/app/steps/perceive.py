"""Perceive step: Chain-of-Thought situation analysis.

The agent receives its visible context and reasons about the current
tactical situation before making any decisions.
"""
from __future__ import annotations

from ..adapters.base import ModelRequest
from ..pipeline import PipelineContext


class PerceiveStep:
    """Asks the model to analyze the current situation using CoT reasoning."""

    @property
    def name(self) -> str:
        return "perceive"

    async def execute(self, ctx: PipelineContext) -> PipelineContext:
        entities_summary = self._summarize_entities(ctx)
        objectives_summary = self._summarize_objectives(ctx)

        prompt = f"""Analyze the current tactical situation. Think step by step.

{ctx.agent_context.scene_summary}

Visible entities:
{entities_summary}
{objectives_summary}
Your character: {ctx.actor_name} ({ctx.role})
Your goals: {', '.join(ctx.goals) if ctx.goals else 'None specified'}
Available actions: {', '.join(str(a) for a in ctx.allowed_actions)}

Consider:
1. What threats exist and their severity?
2. What opportunities are available (objects to inspect, objectives to complete)?
3. What is the tactical priority right now?
4. Any relevant status effects or positioning?

Respond with a concise tactical assessment (2-4 sentences)."""

        request = ModelRequest(
            system_prompt=ctx.system_prompt,
            user_prompt=prompt,
            temperature=max(0.2, ctx.temperature - 0.1),
            max_tokens=4096,
        )

        response = await ctx.adapter.generate(request)

        step_trace = ctx.trace.steps[-1] if ctx.trace.steps else None
        if step_trace and step_trace.step_name == self.name:
            step_trace.model_calls += 1
            step_trace.tokens_used += response.tokens_used

        if response.success:
            ctx.perception = response.raw_text.strip()
        else:
            ctx.perception = ctx.agent_context.scene_summary

        return ctx

    def _summarize_objectives(self, ctx: PipelineContext) -> str:
        """Summarize objectives and flags. Filter out system/config flags."""
        parts: list[str] = []
        
        # Use visible_state to stay consistent
        visible_state = ctx.agent_context.visible_state
        
        if visible_state.objectives:
            parts.append("\nObjectives:")
            for obj in visible_state.objectives:
                parts.append(f"  [{obj.status}] {obj.label}: {obj.summary}")
        
        if visible_state.flags:
            # Filter out system/configuration flags that aren't game objects
            system_flags = {
                "story_seed", "story_genre", "story_themes", "story_difficulty",
                "story_random_seed", "map_complexity", "generate_dynamic_map",
                "difficulty", "random_seed",
            }
            game_flags = {
                k: v for k, v in visible_state.flags.items() 
                if k not in system_flags and not k.startswith("story_")
            }
            incomplete = {k: v for k, v in game_flags.items() if not v}
            if incomplete:
                parts.append(f"\nUninvestigated areas/objects: {', '.join(incomplete.keys())}")
        
        return "\n".join(parts)

    def _summarize_entities(self, ctx: PipelineContext) -> str:
        """Summarize only VISIBLE entities - use agent_context.visible_state, not full state."""
        parts: list[str] = []
        
        # Use visible_state which has been filtered for line-of-sight
        visible_state = ctx.agent_context.visible_state
        
        # Get actor's position for distance calculations
        actor_pos = None
        if ctx.actor_id in visible_state.characters:
            actor = visible_state.characters[ctx.actor_id]
            if actor.position:
                actor_pos = (actor.position.x, actor.position.y)
        
        for cid, char in visible_state.characters.items():
            if not char.alive or char.hp <= 0:
                parts.append(f"- {char.name} ({cid}): DEAD")
                continue
            pos_str = f"({char.position.x},{char.position.y})" if char.position else "unknown"
            status = ", ".join(char.status_effects) if char.status_effects else "none"
            parts.append(f"- {char.name} ({cid}): HP {char.hp}/{char.max_hp}, AC {char.ac}, pos {pos_str}, status: {status}")

        for nid, npc in visible_state.npcs.items():
            if not npc.alive or npc.hp <= 0:
                parts.append(f"- {npc.name} ({nid}): DEAD")
                continue
            pos_str = f"({npc.position.x},{npc.position.y})" if npc.position else "unknown"
            status = ", ".join(npc.status_effects) if npc.status_effects else "none"
            
            # Calculate distance for hostile NPCs
            distance_info = ""
            if actor_pos and npc.position and npc.disposition == "hostile":
                dist = max(abs(npc.position.x - actor_pos[0]), abs(npc.position.y - actor_pos[1]))
                if dist == 1:
                    distance_info = ", DIST=1 (ADJACENT)"
                else:
                    distance_info = f", DIST={dist}"
            
            parts.append(f"- {npc.name} ({nid}): HP {npc.hp}/{npc.max_hp}, AC {npc.ac}, pos {pos_str}, {npc.disposition}{distance_info}, status: {status}")

        return "\n".join(parts) if parts else "No entities visible."
