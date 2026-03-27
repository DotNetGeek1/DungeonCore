"""Pending action store and human turn coordination for human-in-the-loop."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone

from shared_schemas.actions import PlayerTurn


@dataclass
class PendingHumanAction:
    session_id: str
    actor_id: str
    submitted_turn: PlayerTurn | None = None
    event: asyncio.Event = field(default_factory=asyncio.Event)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class HumanActionStore:
    """In-memory store for pending human actions, keyed by session_id."""

    def __init__(self) -> None:
        self._pending: dict[str, PendingHumanAction] = {}

    def create_pending(self, session_id: str, actor_id: str) -> PendingHumanAction:
        pending = PendingHumanAction(session_id=session_id, actor_id=actor_id)
        self._pending[session_id] = pending
        return pending

    def get_pending(self, session_id: str) -> PendingHumanAction | None:
        return self._pending.get(session_id)

    def submit_action(self, session_id: str, turn: PlayerTurn) -> bool:
        pending = self._pending.get(session_id)
        if pending is None:
            return False
        pending.submitted_turn = turn
        pending.event.set()
        return True

    def clear_pending(self, session_id: str) -> None:
        self._pending.pop(session_id, None)

    async def wait_for_action(
        self, session_id: str, timeout_seconds: float = 120.0
    ) -> PlayerTurn | None:
        """Wait for a human to submit an action, returning None on timeout."""
        pending = self._pending.get(session_id)
        if pending is None:
            return None

        try:
            await asyncio.wait_for(pending.event.wait(), timeout=timeout_seconds)
            return pending.submitted_turn
        except asyncio.TimeoutError:
            return None
        finally:
            self.clear_pending(session_id)


@dataclass
class OverridePendingAction:
    """Holds a director override that replaces a proposed action before resolution."""
    session_id: str
    turn: PlayerTurn


class OverrideStore:
    """In-memory store for director action overrides."""

    def __init__(self) -> None:
        self._overrides: dict[str, OverridePendingAction] = {}

    def set_override(self, session_id: str, turn: PlayerTurn) -> None:
        self._overrides[session_id] = OverridePendingAction(
            session_id=session_id, turn=turn
        )

    def consume_override(self, session_id: str) -> PlayerTurn | None:
        override = self._overrides.pop(session_id, None)
        return override.turn if override else None

    def has_override(self, session_id: str) -> bool:
        return session_id in self._overrides


class LastResolutionStore:
    """Stores the last resolution data per session for narration re-runs."""

    def __init__(self) -> None:
        self._resolutions: dict[str, dict] = {}

    def store(self, session_id: str, resolution_data: dict) -> None:
        self._resolutions[session_id] = resolution_data

    def get(self, session_id: str) -> dict | None:
        return self._resolutions.get(session_id)

    def clear(self, session_id: str) -> None:
        self._resolutions.pop(session_id, None)


@dataclass
class RecentActionRecord:
    """Record of a recent action for detecting repetitive behavior."""
    action_type: str
    target_id: str | None
    turn_number: int


class ActionHistoryStore:
    """Tracks recent actions per actor per session to detect repetitive loops."""

    MAX_HISTORY_PER_ACTOR = 5

    def __init__(self) -> None:
        # session_id -> actor_id -> list of recent actions
        self._history: dict[str, dict[str, list[RecentActionRecord]]] = {}

    def record_action(
        self,
        session_id: str,
        actor_id: str,
        action_type: str,
        target_id: str | None,
        turn_number: int,
    ) -> None:
        """Record an action for an actor."""
        if session_id not in self._history:
            self._history[session_id] = {}
        if actor_id not in self._history[session_id]:
            self._history[session_id][actor_id] = []

        record = RecentActionRecord(
            action_type=action_type,
            target_id=target_id,
            turn_number=turn_number,
        )
        self._history[session_id][actor_id].append(record)

        # Keep only the most recent actions
        if len(self._history[session_id][actor_id]) > self.MAX_HISTORY_PER_ACTOR:
            self._history[session_id][actor_id] = self._history[session_id][actor_id][-self.MAX_HISTORY_PER_ACTOR:]

    def get_recent_actions(
        self, session_id: str, actor_id: str
    ) -> list[RecentActionRecord]:
        """Get recent actions for an actor."""
        if session_id not in self._history:
            return []
        return self._history.get(session_id, {}).get(actor_id, [])

    def clear_session(self, session_id: str) -> None:
        """Clear all action history for a session."""
        self._history.pop(session_id, None)
