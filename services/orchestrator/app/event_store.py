"""Event store implementations for the orchestrator."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from shared_config.persistence import EventRepository

logger = logging.getLogger(__name__)


class InMemoryEventStore:
    """Stores events in memory, keyed by session_id. Implements the EventPublisher protocol."""

    def __init__(self) -> None:
        self._events: dict[str, list[dict]] = defaultdict(list)
        self._initial_states: dict[str, dict] = {}

    async def publish(self, event: object) -> None:
        serialized = self._serialize(event)
        session_id = serialized.get("session_id", "unknown")
        self._events[session_id].append(serialized)

    def store_initial_state(self, session_id: str, state: object) -> None:
        if hasattr(state, "model_dump"):
            self._initial_states[session_id] = state.model_dump(mode="json")
        elif isinstance(state, dict):
            self._initial_states[session_id] = state

    def get_initial_state(self, session_id: str) -> dict | None:
        return self._initial_states.get(session_id)

    def list_events(
        self,
        session_id: str,
        *,
        limit: int = 500,
        event_type: str | None = None,
        actor_id: str | None = None,
    ) -> list[dict]:
        events = self._events.get(session_id, [])

        if event_type:
            events = [e for e in events if e.get("event_type") == event_type]

        if actor_id:
            events = [
                e for e in events
                if e.get("payload", {}).get("actor_id") == actor_id
            ]

        return events[:limit]

    def get_replay_data(self, session_id: str) -> dict:
        events = self._events.get(session_id, [])
        initial_state = self._initial_states.get(session_id)

        turn_numbers = {e.get("turn_number", 0) for e in events}
        total_turns = max(turn_numbers) if turn_numbers else 0

        return {
            "session_id": session_id,
            "initial_state": initial_state,
            "events": events,
            "total_events": len(events),
            "total_turns": total_turns,
        }

    def event_count(self, session_id: str) -> int:
        return len(self._events.get(session_id, []))

    def _serialize(self, event: object) -> dict:
        if hasattr(event, "model_dump"):
            return event.model_dump(mode="json")
        if hasattr(event, "__dict__"):
            return dict(event.__dict__)
        return {"type": str(type(event).__name__)}


class PersistentEventStore:
    """Wraps InMemoryEventStore and persists events to database when available.
    
    This composite store ensures events are always available in-memory for fast access
    while also persisting them to the database for durability across restarts.
    """

    def __init__(
        self,
        memory_store: InMemoryEventStore,
        event_repo: "EventRepository | None" = None,
    ) -> None:
        self._memory = memory_store
        self._repo = event_repo

    async def publish(self, event: object) -> None:
        """Publish event to both in-memory store and database."""
        await self._memory.publish(event)
        
        if self._repo is not None:
            try:
                serialized = self._memory._serialize(event)
                self._repo.append(serialized)
            except Exception as e:
                logger.warning("Failed to persist event to database: %s", e)

    def store_initial_state(self, session_id: str, state: object) -> None:
        """Store initial state (delegated to memory store)."""
        self._memory.store_initial_state(session_id, state)

    def get_initial_state(self, session_id: str) -> dict | None:
        """Get initial state (delegated to memory store)."""
        return self._memory.get_initial_state(session_id)

    def list_events(
        self,
        session_id: str,
        *,
        limit: int = 500,
        event_type: str | None = None,
        actor_id: str | None = None,
    ) -> list[dict]:
        """List events (from memory for speed, falls back to DB if empty)."""
        events = self._memory.list_events(
            session_id, limit=limit, event_type=event_type, actor_id=actor_id
        )
        
        if not events and self._repo is not None:
            try:
                events = self._repo.list_for_session(
                    session_id, limit=limit, event_type=event_type, actor_id=actor_id
                )
            except Exception as e:
                logger.warning("Failed to load events from database: %s", e)
        
        return events

    def get_replay_data(self, session_id: str) -> dict:
        """Get replay data (delegated to memory store)."""
        return self._memory.get_replay_data(session_id)

    def event_count(self, session_id: str) -> int:
        """Get event count (delegated to memory store)."""
        return self._memory.event_count(session_id)
