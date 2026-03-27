from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, TYPE_CHECKING

from shared_schemas.state import GameState

if TYPE_CHECKING:
    from game_rules import RulesLoader


@dataclass
class ToolParameter:
    name: str
    type: str
    description: str
    required: bool = True
    enum: list[str] | None = None


@dataclass
class AgentTool:
    """A deterministic tool that an LLM agent can invoke."""

    name: str
    description: str
    parameters: list[ToolParameter] = field(default_factory=list)
    handler: Callable[..., str] | None = None

    def to_openai_schema(self) -> dict[str, Any]:
        properties: dict[str, Any] = {}
        required: list[str] = []

        for param in self.parameters:
            prop: dict[str, Any] = {
                "type": param.type,
                "description": param.description,
            }
            if param.enum:
                prop["enum"] = param.enum
            properties[param.name] = prop
            if param.required:
                required.append(param.name)

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }

    def execute(self, **kwargs: Any) -> str:
        if self.handler is None:
            return json.dumps({"error": f"Tool '{self.name}' has no handler"})
        return self.handler(**kwargs)


class ToolRegistry:
    """Registry of tools available to agents during pipeline execution."""

    def __init__(self) -> None:
        self._tools: dict[str, AgentTool] = {}

    def register(self, tool: AgentTool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> AgentTool | None:
        return self._tools.get(name)

    def list_tools(self) -> list[AgentTool]:
        return list(self._tools.values())

    def get_openai_tools_schema(self) -> list[dict[str, Any]]:
        return [t.to_openai_schema() for t in self._tools.values()]

    def execute_tool(self, name: str, arguments: dict[str, Any]) -> str:
        tool = self._tools.get(name)
        if tool is None:
            return json.dumps({"error": f"Unknown tool: {name}"})
        try:
            return tool.execute(**arguments)
        except Exception as e:
            return json.dumps({"error": f"Tool execution failed: {e}"})

    @property
    def tool_names(self) -> list[str]:
        return list(self._tools.keys())


def create_default_registry(
    rules: RulesLoader | None = None,
    state: GameState | None = None,
    recent_messages: list | None = None,
) -> ToolRegistry:
    from .rules_tools import register_rules_tools
    from .state_tools import register_state_tools
    from .validation_tools import register_validation_tools

    registry = ToolRegistry()
    register_rules_tools(registry, rules)
    register_state_tools(registry, state, recent_messages=recent_messages)
    register_validation_tools(registry, state)
    return registry


def create_dm_registry(
    rules: RulesLoader | None = None,
    state: GameState | None = None,
    recent_messages: list | None = None,
) -> ToolRegistry:
    """Create a tool registry for DM agents, which includes map manipulation tools."""
    from .rules_tools import register_rules_tools
    from .state_tools import register_state_tools
    from .validation_tools import register_validation_tools
    from .map_tools import register_map_tools

    registry = ToolRegistry()
    register_rules_tools(registry, rules)
    register_state_tools(registry, state, recent_messages=recent_messages)
    register_validation_tools(registry, state)
    register_map_tools(registry, state)
    return registry
