"""Pipeline trace storage: in-memory with optional Postgres persistence.

Stores PipelineTrace objects from pipeline invocations and makes them
queryable for the /traces endpoint and future observability tooling.
"""
from __future__ import annotations

import json
from collections import deque
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from .pipeline import PipelineTrace, StepTrace, ToolCall


class PipelineTraceStore:
    """Stores pipeline traces in memory with a bounded buffer."""

    def __init__(self, max_traces: int = 500) -> None:
        self._traces: deque[PipelineTrace] = deque(maxlen=max_traces)

    def store(self, trace: PipelineTrace) -> None:
        self._traces.append(trace)

    def get_all(self) -> list[PipelineTrace]:
        return list(self._traces)

    def get_by_agent(self, agent_id: str) -> list[PipelineTrace]:
        return [t for t in self._traces if t.agent_id == agent_id]

    def get_recent(self, count: int = 20) -> list[PipelineTrace]:
        traces = list(self._traces)
        return traces[-count:]

    def serialize(self, trace: PipelineTrace) -> dict[str, Any]:
        return {
            "agent_id": trace.agent_id,
            "invocation_mode": trace.invocation_mode,
            "provider": trace.provider,
            "model": trace.model,
            "total_latency_ms": trace.total_latency_ms,
            "total_tokens": trace.total_tokens,
            "total_model_calls": trace.total_model_calls,
            "memories_retrieved": trace.memories_retrieved,
            "final_validation": trace.final_validation,
            "error": trace.error,
            "started_at": trace.started_at.isoformat(),
            "steps": [
                {
                    "step_name": s.step_name,
                    "started_at": s.started_at.isoformat(),
                    "finished_at": s.finished_at.isoformat() if s.finished_at else None,
                    "latency_ms": s.latency_ms,
                    "model_calls": s.model_calls,
                    "tokens_used": s.tokens_used,
                    "tool_calls": [
                        {
                            "tool_name": tc.tool_name,
                            "arguments": tc.arguments,
                            "result_preview": tc.result[:200] if tc.result else "",
                            "latency_ms": tc.latency_ms,
                        }
                        for tc in s.tool_calls
                    ],
                    "reflection_verdict": s.reflection_verdict,
                    "error": s.error,
                    "metadata": {k: str(v)[:200] for k, v in s.metadata.items()},
                }
                for s in trace.steps
            ],
        }

    def serialize_all(self) -> list[dict[str, Any]]:
        return [self.serialize(t) for t in self._traces]

    @property
    def count(self) -> int:
        return len(self._traces)

    def clear(self) -> None:
        self._traces.clear()
