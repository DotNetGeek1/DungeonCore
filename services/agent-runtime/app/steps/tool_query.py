"""Tool query step: ReAct-style tool execution loop.

The model can call tools (spell lookups, distance checks, etc.) to gather
information before making a decision. The loop continues until the model
stops requesting tools or the iteration budget is exhausted.
"""
from __future__ import annotations

import json
import time
from typing import Any

from ..adapters.base import ModelRequest, ToolCallResult
from ..pipeline import PipelineContext, ToolCall
from ..tools.registry import ToolRegistry


MAX_TOOL_ITERATIONS = 6


class ToolQueryStep:
    """Executes a ReAct-style tool-calling loop with the model."""

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    @property
    def name(self) -> str:
        return "tool_query"

    async def execute(self, ctx: PipelineContext) -> PipelineContext:
        tools_schema = self._registry.get_openai_tools_schema()
        if not tools_schema:
            return ctx

        tool_context_parts = []
        if ctx.perception:
            tool_context_parts.append(f"Tactical assessment:\n{ctx.perception}")

        # Check if this is a map generation request
        # The orchestrator includes map generation instructions in system_prompt
        combined_context = (ctx.system_prompt + " " + ctx.user_prompt).lower()
        is_map_generation = "init_map" in combined_context or "generate_room" in combined_context
        
        if is_map_generation:
            prompt = f"""{'\n'.join(tool_context_parts)}

You MUST use the map generation tools to create the dungeon. Start by calling init_map, then generate_room for each room, connect_rooms to link them, and populate_room to add content. These are function calls you make, not text descriptions."""
        else:
            prompt = f"""{'\n'.join(tool_context_parts)}

You may call tools to look up game rules, check spell details, calculate distances, or verify targets before deciding your action. Call the tools you need, or respond directly if you have enough information.

Available information is also in your context — only use tools if you need specific rule details."""
        
        print(f"[ToolQueryStep] is_map_generation={is_map_generation}, tools_count={len(tools_schema)}")
        print(f"[ToolQueryStep] user_prompt preview: {ctx.user_prompt[:300] if ctx.user_prompt else 'empty'}")

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": ctx.system_prompt},
            {"role": "user", "content": ctx.user_prompt},
        ]
        if ctx.perception:
            messages.append({"role": "assistant", "content": ctx.perception})
        messages.append({"role": "user", "content": prompt})

        for iteration in range(MAX_TOOL_ITERATIONS):
            request = ModelRequest(
                system_prompt=ctx.system_prompt,
                user_prompt="",
                messages=messages,
                temperature=0.1,
                max_tokens=4096,
                tools=tools_schema,
            )

            response = await ctx.adapter.generate(request)

            step_trace = ctx.trace.steps[-1] if ctx.trace.steps else None
            if step_trace and step_trace.step_name == self.name:
                step_trace.model_calls += 1
                step_trace.tokens_used += response.tokens_used

            # Always capture raw_text for potential speech extraction
            if response.raw_text:
                ctx.reasoning += f"\n{response.raw_text.strip()}"
            
            if not response.success or not response.has_tool_calls:
                break

            assistant_msg: dict[str, Any] = {"role": "assistant", "content": response.raw_text or ""}
            if response.tool_calls:
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
                    }
                    for tc in response.tool_calls
                ]
            messages.append(assistant_msg)

            for tc in response.tool_calls:
                start = time.perf_counter()
                result = self._registry.execute_tool(tc.name, tc.arguments)
                elapsed = int((time.perf_counter() - start) * 1000)

                ctx.tool_results[tc.name] = result

                if step_trace and step_trace.step_name == self.name:
                    step_trace.tool_calls.append(ToolCall(
                        tool_name=tc.name,
                        arguments=tc.arguments,
                        result=result[:500],
                        latency_ms=elapsed,
                    ))

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })

        ctx.messages_history = messages
        return ctx
