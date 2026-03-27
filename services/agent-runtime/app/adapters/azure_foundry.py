from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

import httpx

from .base import ModelAdapter, ModelRequest, ModelResponse, TokenCallback, ToolCallRequest


@dataclass
class AzureAIFoundryConfig:
    endpoint: str = "https://example.services.ai.azure.com"
    api_key: str = ""
    model: str = "gpt-4"
    timeout_seconds: float = 120.0
    api_version: str = "2024-02-15-preview"


class AzureAIFoundryAdapter(ModelAdapter):
    def __init__(self, config: AzureAIFoundryConfig | None = None) -> None:
        self.config = config or AzureAIFoundryConfig()
        self._client = httpx.AsyncClient(timeout=self.config.timeout_seconds)

    @property
    def provider_name(self) -> str:
        return "azure_ai_foundry"

    async def generate(self, request: ModelRequest) -> ModelResponse:
        start_time = time.perf_counter()

        if not self.config.api_key:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            return ModelResponse(
                raw_text="",
                latency_ms=elapsed_ms,
                provider=self.provider_name,
                model=self.config.model,
                error="Azure AI Foundry adapter not configured (missing API key)",
            )

        if not self.config.endpoint or self.config.endpoint == "https://example.services.ai.azure.com":
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            return ModelResponse(
                raw_text="",
                latency_ms=elapsed_ms,
                provider=self.provider_name,
                model=self.config.model,
                error="Azure AI Foundry adapter not configured (missing or invalid endpoint)",
            )

        if request.messages:
            messages = list(request.messages)
        else:
            messages = [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.user_prompt},
            ]
            for tool_result in request.tool_results:
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_result.tool_call_id,
                    "content": tool_result.result,
                })

        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }

        if request.stop_sequences:
            payload["stop"] = request.stop_sequences

        if request.response_format and not request.tools:
            payload["response_format"] = request.response_format

        if request.tools:
            payload["tools"] = request.tools
            payload["tool_choice"] = "auto"
            tool_names = [t.get("function", {}).get("name", "?") for t in request.tools]
            print(f"[AzureFoundry] Sending request with {len(request.tools)} tools: {tool_names}")

        headers = {
            "Content-Type": "application/json",
            "api-key": self.config.api_key,
        }

        try:
            url = f"{self.config.endpoint}/openai/deployments/{self.config.model}/chat/completions?api-version={self.config.api_version}"
            print(f"[AzureFoundry] POST to {url}")
            response = await self._client.post(url, json=payload, headers=headers)
            response.raise_for_status()

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
                raw_tool_calls = message.get("tool_calls", [])
                print(f"[AzureFoundry] finish_reason={finish_reason}, raw_tool_calls={len(raw_tool_calls)}")
                if raw_text:
                    print(f"[AzureFoundry] raw_text preview: {raw_text[:500]}")
                for tc in raw_tool_calls:
                    fn = tc.get("function", {})
                    args_str = fn.get("arguments", "{}")
                    print(f"[AzureFoundry] Tool call: {fn.get('name')} with args: {args_str[:200]}")
                    try:
                        args = json.loads(args_str) if isinstance(args_str, str) else args_str
                    except json.JSONDecodeError:
                        args = {}
                    tool_calls.append(ToolCallRequest(
                        id=tc.get("id", ""),
                        name=fn.get("name", ""),
                        arguments=args,
                    ))

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
            status_code = e.response.status_code
            
            if status_code == 401:
                error_msg = "Authentication failed: invalid API key"
            elif status_code == 403:
                error_msg = "Authorization failed: insufficient permissions"
            elif status_code == 429:
                error_msg = "Rate limit exceeded: too many requests"
            elif status_code == 404:
                error_msg = f"Model deployment '{self.config.model}' not found"
            else:
                error_msg = f"HTTP error {status_code}: {e.response.text}"
            
            return ModelResponse(
                raw_text="",
                latency_ms=elapsed_ms,
                provider=self.provider_name,
                model=self.config.model,
                error=error_msg,
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

        if not self.config.api_key or (
            not self.config.endpoint
            or self.config.endpoint == "https://example.services.ai.azure.com"
        ):
            return await self.generate(request)

        if request.messages:
            messages = list(request.messages)
        else:
            messages = [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.user_prompt},
            ]
            for tool_result in request.tool_results:
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_result.tool_call_id,
                    "content": tool_result.result,
                })

        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": True,
        }

        if request.stop_sequences:
            payload["stop"] = request.stop_sequences

        if request.response_format and not request.tools:
            payload["response_format"] = request.response_format

        if request.tools:
            payload["tools"] = request.tools
            payload["tool_choice"] = "auto"

        headers = {
            "Content-Type": "application/json",
            "api-key": self.config.api_key,
        }

        try:
            url = f"{self.config.endpoint}/openai/deployments/{self.config.model}/chat/completions?api-version={self.config.api_version}"
            full_text = ""
            finish_reason = "stop"

            async with self._client.stream("POST", url, json=payload, headers=headers) as response:
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
            tokens_used = len(full_text) // 4
            return ModelResponse(
                raw_text=full_text,
                latency_ms=elapsed_ms,
                provider=self.provider_name,
                model=self.config.model,
                finish_reason=finish_reason,
                tokens_used=tokens_used,
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
            # For streaming responses, we can't access .text directly without reading
            try:
                error_body = await e.response.aread()
                error_text = error_body.decode('utf-8', errors='replace')
            except Exception:
                error_text = "(unable to read response body)"
            return ModelResponse(
                raw_text="", latency_ms=elapsed_ms,
                provider=self.provider_name, model=self.config.model,
                error=f"HTTP error {e.response.status_code}: {error_text}",
            )
        except Exception as e:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            return ModelResponse(
                raw_text="", latency_ms=elapsed_ms,
                provider=self.provider_name, model=self.config.model,
                error=str(e),
            )

    async def health_check(self) -> bool:
        if not self.config.api_key:
            return False

        try:
            headers = {"api-key": self.config.api_key}
            url = f"{self.config.endpoint}/openai/models?api-version={self.config.api_version}"
            response = await self._client.get(url, headers=headers, timeout=5.0)
            return response.status_code == 200
        except Exception:
            return False

    async def close(self) -> None:
        await self._client.aclose()
