from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable, Awaitable


@dataclass
class ToolCallRequest:
    """A tool call returned by the model that needs to be executed."""
    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolCallResult:
    """Result of executing a tool, to be fed back to the model."""
    tool_call_id: str
    name: str
    result: str


@dataclass
class ModelRequest:
    system_prompt: str
    user_prompt: str
    temperature: float = 0.4
    max_tokens: int = 4096
    response_format: dict[str, Any] | None = None
    stop_sequences: list[str] = field(default_factory=list)
    tools: list[dict[str, Any]] = field(default_factory=list)
    messages: list[dict[str, Any]] = field(default_factory=list)
    tool_results: list[ToolCallResult] = field(default_factory=list)


@dataclass
class ModelResponse:
    raw_text: str
    latency_ms: int
    provider: str
    model: str
    finish_reason: str = "stop"
    tokens_used: int = 0
    error: str | None = None
    tool_calls: list[ToolCallRequest] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return self.error is None

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0


TokenCallback = Callable[[str], Awaitable[None]]


class ModelAdapter(ABC):
    @property
    @abstractmethod
    def provider_name(self) -> str:
        pass

    @abstractmethod
    async def generate(self, request: ModelRequest) -> ModelResponse:
        pass

    async def generate_streaming(
        self, request: ModelRequest, on_token: TokenCallback | None = None,
    ) -> ModelResponse:
        """Generate with optional token-by-token streaming callback.
        Default implementation falls back to non-streaming generate."""
        return await self.generate(request)

    @abstractmethod
    async def health_check(self) -> bool:
        pass
