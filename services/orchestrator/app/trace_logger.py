"""Structured per-turn trace collection for observability.

Traces are diagnostic artifacts for debugging -- never canonical game state.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class AgentInvocationRecord:
    agent_id: str
    role: str
    latency_ms: int = 0
    validation_result: str = ""
    retries: int = 0
    error: str | None = None


@dataclass
class TurnTrace:
    session_id: str
    turn_number: int
    active_actor_id: str | None
    context_summary: str = ""
    phase_sequence: list[str] = field(default_factory=list)
    agent_invocations: list[AgentInvocationRecord] = field(default_factory=list)
    action_proposed: str | None = None
    action_validated: bool | None = None
    action_resolved: str | None = None
    narration_summary: str | None = None
    total_latency_ms: int = 0
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None
    errors: list[str] = field(default_factory=list)


class TurnTraceLogger:
    def __init__(self) -> None:
        self._traces: dict[str, list[TurnTrace]] = {}
        self._active: dict[str, TurnTrace] = {}
        self._start_times: dict[str, float] = {}

    def start_turn(
        self,
        session_id: str,
        turn_number: int,
        active_actor_id: str | None,
        context_summary: str = "",
    ) -> None:
        trace = TurnTrace(
            session_id=session_id,
            turn_number=turn_number,
            active_actor_id=active_actor_id,
            context_summary=context_summary,
        )
        self._active[session_id] = trace
        self._start_times[session_id] = time.perf_counter()

    def log_phase(self, session_id: str, phase_name: str) -> None:
        trace = self._active.get(session_id)
        if trace:
            trace.phase_sequence.append(phase_name)

    def log_agent_invocation(
        self,
        session_id: str,
        agent_id: str,
        role: str,
        latency_ms: int = 0,
        validation_result: str = "",
        retries: int = 0,
        error: str | None = None,
    ) -> None:
        trace = self._active.get(session_id)
        if trace:
            trace.agent_invocations.append(AgentInvocationRecord(
                agent_id=agent_id,
                role=role,
                latency_ms=latency_ms,
                validation_result=validation_result,
                retries=retries,
                error=error,
            ))

    def log_action_proposed(self, session_id: str, action_type: str) -> None:
        trace = self._active.get(session_id)
        if trace:
            trace.action_proposed = action_type

    def log_action_validated(self, session_id: str, valid: bool) -> None:
        trace = self._active.get(session_id)
        if trace:
            trace.action_validated = valid

    def log_action_resolved(self, session_id: str, description: str) -> None:
        trace = self._active.get(session_id)
        if trace:
            trace.action_resolved = description

    def log_narration(self, session_id: str, summary: str) -> None:
        trace = self._active.get(session_id)
        if trace:
            trace.narration_summary = summary[:200]

    def log_error(self, session_id: str, error: str) -> None:
        trace = self._active.get(session_id)
        if trace:
            trace.errors.append(error)

    def finalize(self, session_id: str) -> TurnTrace | None:
        trace = self._active.pop(session_id, None)
        if trace is None:
            return None

        start_time = self._start_times.pop(session_id, None)
        if start_time is not None:
            trace.total_latency_ms = int((time.perf_counter() - start_time) * 1000)

        trace.completed_at = datetime.now(timezone.utc)

        if session_id not in self._traces:
            self._traces[session_id] = []
        self._traces[session_id].append(trace)

        return trace

    def get_traces(self, session_id: str) -> list[TurnTrace]:
        return self._traces.get(session_id, [])

    def get_all_traces(self) -> dict[str, list[TurnTrace]]:
        return dict(self._traces)

    def serialize_trace(self, trace: TurnTrace) -> dict:
        return {
            "session_id": trace.session_id,
            "turn_number": trace.turn_number,
            "active_actor_id": trace.active_actor_id,
            "context_summary": trace.context_summary,
            "phase_sequence": trace.phase_sequence,
            "agent_invocations": [
                {
                    "agent_id": inv.agent_id,
                    "role": inv.role,
                    "latency_ms": inv.latency_ms,
                    "validation_result": inv.validation_result,
                    "retries": inv.retries,
                    "error": inv.error,
                }
                for inv in trace.agent_invocations
            ],
            "action_proposed": trace.action_proposed,
            "action_validated": trace.action_validated,
            "action_resolved": trace.action_resolved,
            "narration_summary": trace.narration_summary,
            "total_latency_ms": trace.total_latency_ms,
            "started_at": trace.started_at.isoformat(),
            "completed_at": trace.completed_at.isoformat() if trace.completed_at else None,
            "errors": trace.errors,
        }
