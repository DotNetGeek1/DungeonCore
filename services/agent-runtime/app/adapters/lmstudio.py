from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

import httpx

from .base import ModelAdapter, ModelRequest, ModelResponse, TokenCallback, ToolCallRequest


@dataclass
class LMStudioConfig:
    base_url: str = "http://localhost:1234"
    model: str = "local-model"
    timeout_seconds: float = 120.0
    api_version: str = "v1"


class LMStudioAdapter(ModelAdapter):
    def __init__(self, config: LMStudioConfig | None = None) -> None:
        self.config = config or LMStudioConfig()
        self._client = httpx.AsyncClient(timeout=self.config.timeout_seconds)

    @property
    def provider_name(self) -> str:
        return "lmstudio"

    def _build_messages(self, request: ModelRequest) -> list[dict[str, Any]]:
        if request.messages:
            return list(request.messages)

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": request.system_prompt},
            {"role": "user", "content": request.user_prompt},
        ]

        for tool_result in request.tool_results:
            messages.append({
                "role": "tool",
                "tool_call_id": tool_result.tool_call_id,
                "content": tool_result.result,
            })

        return messages

    def _parse_tool_calls(self, message: dict[str, Any]) -> list[ToolCallRequest]:
        """Parse tool calls from the message, supporting multiple formats."""
        import re
        import uuid
        
        raw_calls = message.get("tool_calls", [])
        parsed: list[ToolCallRequest] = []
        
        # First try OpenAI-style tool_calls array
        for tc in raw_calls:
            fn = tc.get("function", {})
            args_str = fn.get("arguments", "{}")
            try:
                args = json.loads(args_str) if isinstance(args_str, str) else args_str
            except json.JSONDecodeError:
                args = {}
            parsed.append(ToolCallRequest(
                id=tc.get("id", str(uuid.uuid4())),
                name=fn.get("name", ""),
                arguments=args,
            ))
        
        # If no tool_calls in response, try parsing from raw content
        # Some models output <tool_call> XML format in content
        if not parsed:
            content = message.get("content", "") or ""
            
            # Try <tool_call>{"name": ..., "arguments": ...}</tool_call> format
            tool_call_pattern = r'<tool_call>\s*(\{[^}]+\})\s*</tool_call>'
            matches = re.findall(tool_call_pattern, content, re.DOTALL)
            for match in matches:
                try:
                    tc_data = json.loads(match)
                    parsed.append(ToolCallRequest(
                        id=str(uuid.uuid4()),
                        name=tc_data.get("name", ""),
                        arguments=tc_data.get("arguments", {}),
                    ))
                except json.JSONDecodeError:
                    continue
            
            # Try functions.function_name format (seen in logs)
            func_pattern = r'to=functions\.(\w+)[^{]*(\{[^}]+\})'
            func_matches = re.findall(func_pattern, content)
            for func_name, args_str in func_matches:
                try:
                    args = json.loads(args_str)
                    parsed.append(ToolCallRequest(
                        id=str(uuid.uuid4()),
                        name=func_name,
                        arguments=args,
                    ))
                except json.JSONDecodeError:
                    continue
        
        return parsed

    async def generate(self, request: ModelRequest) -> ModelResponse:
        start_time = time.perf_counter()

        messages = self._build_messages(request)

        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": False,
        }

        if request.stop_sequences:
            payload["stop"] = request.stop_sequences

        if request.tools:
            payload["tools"] = request.tools
            payload["tool_choice"] = "auto"
            # Debug: log what tools we're sending
            tool_names = [t.get("function", {}).get("name", "?") for t in request.tools]
            print(f"[LMStudio] Sending request with {len(request.tools)} tools: {tool_names}")

        try:
            url = f"{self.config.base_url}/{self.config.api_version}/chat/completions"
            response = await self._client.post(url, json=payload)
            response.raise_for_status()
            
            # Debug: log raw response
            print(f"[LMStudio] Response status: {response.status_code}")

            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            data = response.json()

            raw_text = ""
            finish_reason = "stop"
            tokens_used = 0
            tool_calls: list[ToolCallRequest] = []

            if "choices" in data and data["choices"]:
                choice = data["choices"][0]
                message = choice.get("message", {})
                raw_text = message.get("content", "") or ""
                finish_reason = choice.get("finish_reason", "stop")
                tool_calls = self._parse_tool_calls(message)
                
                # Debug: log tool call parsing
                if request.tools:
                    print(f"[LMStudio] finish_reason={finish_reason}, raw_tool_calls={message.get('tool_calls')}, parsed={len(tool_calls)}")
                    print(f"[LMStudio] Full message keys: {list(message.keys())}")
                    print(f"[LMStudio] raw_text_preview={raw_text[:500] if raw_text else 'empty'}")

            if "usage" in data:
                tokens_used = data["usage"].get("total_tokens", 0)

            return ModelResponse(
                raw_text=raw_text,
                latency_ms=elapsed_ms,
                provider=self.provider_name,
                model=self.config.model,
                finish_reason=finish_reason,
                tokens_used=tokens_used,
                tool_calls=tool_calls,
            )

        except httpx.TimeoutException:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            return ModelResponse(
                raw_text="",
                latency_ms=elapsed_ms,
                provider=self.provider_name,
                model=self.config.model,
                error="Request timed out",
            )

        except httpx.HTTPStatusError as e:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            return ModelResponse(
                raw_text="",
                latency_ms=elapsed_ms,
                provider=self.provider_name,
                model=self.config.model,
                error=f"HTTP error {e.response.status_code}: {e.response.text}",
            )

        except Exception as e:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            return ModelResponse(
                raw_text="",
                latency_ms=elapsed_ms,
                provider=self.provider_name,
                model=self.config.model,
                error=str(e),
            )

    async def generate_streaming(
        self, request: ModelRequest, on_token: TokenCallback | None = None,
    ) -> ModelResponse:
        if on_token is None:
            return await self.generate(request)

        start_time = time.perf_counter()
        messages = self._build_messages(request)

        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": True,
        }

        if request.stop_sequences:
            payload["stop"] = request.stop_sequences

        if request.tools:
            payload["tools"] = request.tools
            payload["tool_choice"] = "auto"

        try:
            url = f"{self.config.base_url}/{self.config.api_version}/chat/completions"
            full_text = ""
            finish_reason = "stop"

            async with self._client.stream("POST", url, json=payload) as response:
                response.raise_for_status()
                buffer = ""
                async for chunk in response.aiter_text():
                    buffer += chunk
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        line = line.strip()
                        if not line or not line.startswith("data:"):
                            continue
                        data_str = line[5:].strip()
                        if data_str == "[DONE]":
                            continue
                        try:
                            data = json.loads(data_str)
                            if "choices" in data and data["choices"]:
                                choice = data["choices"][0]
                                delta = choice.get("delta", {})
                                content = delta.get("content", "")
                                if content:
                                    full_text += content
                                    await on_token(content)
                                fr = choice.get("finish_reason")
                                if fr:
                                    finish_reason = fr
                        except json.JSONDecodeError:
                            continue

            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            return ModelResponse(
                raw_text=full_text,
                latency_ms=elapsed_ms,
                provider=self.provider_name,
                model=self.config.model,
                finish_reason=finish_reason,
                tokens_used=len(full_text) // 4,
            )

        except httpx.TimeoutException:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            return ModelResponse(
                raw_text="", latency_ms=elapsed_ms,
                provider=self.provider_name, model=self.config.model,
                error="Request timed out",
            )
        except httpx.HTTPStatusError as e:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            return ModelResponse(
                raw_text="", latency_ms=elapsed_ms,
                provider=self.provider_name, model=self.config.model,
                error=f"HTTP error {e.response.status_code}: {e.response.text}",
            )
        except Exception as e:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            return ModelResponse(
                raw_text="", latency_ms=elapsed_ms,
                provider=self.provider_name, model=self.config.model,
                error=str(e),
            )

    async def health_check(self) -> bool:
        try:
            url = f"{self.config.base_url}/{self.config.api_version}/models"
            response = await self._client.get(url, timeout=5.0)
            return response.status_code == 200
        except Exception:
            return False

    async def close(self) -> None:
        await self._client.aclose()
