from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from shared_schemas.actions import PlayerTurn

from .adapters.base import ModelAdapter, ModelRequest, ModelResponse
from .validation import OutputValidator

logger = logging.getLogger(__name__)


@dataclass
class RetryConfig:
    max_retries: int = 2
    retry_delay_ms: int = 500


@dataclass
class InvocationTrace:
    agent_id: str
    provider: str
    model: str
    prompt_hash: str
    context_hash: str
    validation_result: str
    retries: int
    latency_ms: int
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    error: str | None = None
    raw_response_preview: str | None = None
    parsed_action_type: str | None = None
    selected_memories_count: int = 0


def _hash_string(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()[:16]


class RetryHandler:
    def __init__(
        self,
        adapter: ModelAdapter,
        validator: OutputValidator,
        config: RetryConfig | None = None,
    ) -> None:
        self.adapter = adapter
        self.validator = validator
        self.config = config or RetryConfig()
        self._traces: list[InvocationTrace] = []

    async def invoke_with_retry(
        self,
        request: ModelRequest,
        agent_id: str,
        context_summary: str = "",
    ) -> tuple[PlayerTurn | None, InvocationTrace]:
        start_time = time.perf_counter()
        retries = 0
        last_error: str | None = None
        last_response: ModelResponse | None = None

        prompt_hash = _hash_string(request.system_prompt + request.user_prompt)
        context_hash = _hash_string(context_summary)

        for attempt in range(self.config.max_retries + 1):
            response = await self.adapter.generate(request)
            last_response = response

            if not response.success:
                last_error = response.error
                retries = attempt
                logger.warning(
                    "[retry] LLM error on attempt %d/%d for agent=%s: %s",
                    attempt + 1, self.config.max_retries + 1, agent_id, response.error,
                )
                if attempt < self.config.max_retries:
                    await self._delay()
                continue

            validation = self.validator.validate_player_turn(response.raw_text)

            if validation.valid and validation.parsed:
                elapsed_ms = int((time.perf_counter() - start_time) * 1000)
                parsed_action = None
                if validation.parsed.action:
                    parsed_action = str(validation.parsed.action.type.value)
                trace = InvocationTrace(
                    agent_id=agent_id,
                    provider=self.adapter.provider_name,
                    model=last_response.model if last_response else "unknown",
                    prompt_hash=prompt_hash,
                    context_hash=context_hash,
                    validation_result="valid",
                    retries=retries,
                    latency_ms=elapsed_ms,
                    raw_response_preview=response.raw_text[:200] if response.raw_text else None,
                    parsed_action_type=parsed_action,
                )
                self._traces.append(trace)
                return validation.parsed, trace

            last_error = "; ".join(validation.errors)
            retries = attempt
            logger.warning(
                "[retry] Validation failed on attempt %d/%d for agent=%s: %s | raw=%.200s",
                attempt + 1, self.config.max_retries + 1, agent_id, last_error, response.raw_text,
            )

            if attempt < self.config.max_retries:
                await self._delay()

        elapsed_ms = int((time.perf_counter() - start_time) * 1000)

        logger.error(
            "[retry] All %d attempts exhausted for agent=%s — returning None. Last error: %s",
            self.config.max_retries + 1, agent_id, last_error,
        )

        trace = InvocationTrace(
            agent_id=agent_id,
            provider=self.adapter.provider_name,
            model=last_response.model if last_response else "unknown",
            prompt_hash=prompt_hash,
            context_hash=context_hash,
            validation_result="failed",
            retries=retries,
            latency_ms=elapsed_ms,
            error=last_error,
            raw_response_preview=(last_response.raw_text[:200] if last_response and last_response.raw_text else None),
        )
        self._traces.append(trace)

        return None, trace

    async def _delay(self) -> None:
        import asyncio
        await asyncio.sleep(self.config.retry_delay_ms / 1000.0)

    def get_traces(self) -> list[InvocationTrace]:
        return self._traces.copy()

    def clear_traces(self) -> None:
        self._traces.clear()


def get_retry_handler(
    adapter: ModelAdapter,
    validator: OutputValidator,
    config: RetryConfig | None = None,
) -> RetryHandler:
    return RetryHandler(adapter, validator, config)
