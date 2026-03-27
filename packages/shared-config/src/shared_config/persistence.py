from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from pydantic import TypeAdapter
from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    and_,
    create_engine,
    desc,
    insert,
    select,
)
from sqlalchemy.engine import Engine

from shared_schemas import (
    ActionRecord,
    GameEvent,
    GameState,
    MemoryEntry,
    StateSnapshotRecord,
    TableMessage,
)

metadata = MetaData()

campaigns = Table(
    "campaigns",
    metadata,
    Column("id", String(255), primary_key=True),
    Column("name", String(255), nullable=False),
    Column("payload", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, default=datetime.utcnow),
)

scenes = Table(
    "scenes",
    metadata,
    Column("id", String(255), primary_key=True),
    Column("campaign_id", String(255), ForeignKey("campaigns.id"), nullable=False, index=True),
    Column("name", String(255), nullable=False),
    Column("payload", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, default=datetime.utcnow),
)

sessions = Table(
    "sessions",
    metadata,
    Column("id", String(255), primary_key=True),
    Column("campaign_id", String(255), ForeignKey("campaigns.id"), nullable=False, index=True),
    Column("scene_id", String(255), ForeignKey("scenes.id"), nullable=False, index=True),
    Column("status", String(50), nullable=False, index=True),
    Column("payload", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, default=datetime.utcnow),
    Column("updated_at", DateTime(timezone=True), nullable=False, default=datetime.utcnow),
)

actors = Table(
    "actors",
    metadata,
    Column("id", String(255), primary_key=True),
    Column("session_id", String(255), ForeignKey("sessions.id"), nullable=False, index=True),
    Column("scene_id", String(255), ForeignKey("scenes.id"), nullable=False, index=True),
    Column("role", String(50), nullable=False, index=True),
    Column("name", String(255), nullable=False),
    Column("payload", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, default=datetime.utcnow),
)

character_state_snapshots = Table(
    "character_state_snapshots",
    metadata,
    Column("id", String(255), primary_key=True),
    Column("session_id", String(255), ForeignKey("sessions.id"), nullable=False, index=True),
    Column("scene_id", String(255), ForeignKey("scenes.id"), nullable=False, index=True),
    Column("turn_number", Integer, nullable=False, index=True),
    Column("active_actor_id", String(255), nullable=True, index=True),
    Column("payload", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

events = Table(
    "events",
    metadata,
    Column("id", String(255), primary_key=True),
    Column("session_id", String(255), ForeignKey("sessions.id"), nullable=False, index=True),
    Column("turn_number", Integer, nullable=False, index=True),
    Column("event_type", String(100), nullable=False, index=True),
    Column("actor_id", String(255), nullable=True, index=True),
    Column("trace_id", String(255), nullable=False),
    Column("correlation_id", String(255), nullable=False),
    Column("payload", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, index=True),
)

messages = Table(
    "messages",
    metadata,
    Column("id", String(255), primary_key=True),
    Column("session_id", String(255), ForeignKey("sessions.id"), nullable=False, index=True),
    Column("scene_id", String(255), ForeignKey("scenes.id"), nullable=False, index=True),
    Column("sender_id", String(255), nullable=False, index=True),
    Column("channel", String(50), nullable=False, index=True),
    Column("visibility", String(50), nullable=False, index=True),
    Column("recipient_ids", JSON, nullable=False),
    Column("turn_number", Integer, nullable=False, index=True),
    Column("payload", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, index=True),
)

memory_entries = Table(
    "memory_entries",
    metadata,
    Column("id", String(255), primary_key=True),
    Column("session_id", String(255), ForeignKey("sessions.id"), nullable=False, index=True),
    Column("actor_id", String(255), nullable=False, index=True),
    Column("memory_type", String(50), nullable=False, index=True),
    Column("importance", Integer, nullable=False, index=True),
    Column("visibility", String(50), nullable=False, index=True),
    Column("tags", JSON, nullable=False),
    Column("payload", JSON, nullable=False),
    Column("created_at_turn", Integer, nullable=False, index=True),
)

action_records = Table(
    "action_records",
    metadata,
    Column("id", String(255), primary_key=True),
    Column("session_id", String(255), ForeignKey("sessions.id"), nullable=False, index=True),
    Column("actor_id", String(255), nullable=False, index=True),
    Column("turn_number", Integer, nullable=False, index=True),
    Column("action_type", String(50), nullable=False, index=True),
    Column("status", String(50), nullable=False, index=True),
    Column("source", String(50), nullable=False, index=True),
    Column("event_id", String(255), nullable=True, index=True),
    Column("payload", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, index=True),
)

ai_invocations = Table(
    "ai_invocations",
    metadata,
    Column("id", String(255), primary_key=True),
    Column("session_id", String(255), ForeignKey("sessions.id"), nullable=False, index=True),
    Column("turn_number", Integer, nullable=False, index=True),
    Column("phase", String(50), nullable=False),
    Column("actor_id", String(255), nullable=False, index=True),
    Column("actor_name", String(255), nullable=True),
    Column("invocation_mode", String(50), nullable=True),
    Column("model", String(100), nullable=True),
    Column("prompt_tokens", Integer, nullable=True),
    Column("completion_tokens", Integer, nullable=True),
    Column("latency_ms", Integer, nullable=True),
    Column("success", Boolean, nullable=False),
    Column("error", Text, nullable=True),
    Column("response_payload", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, index=True),
)


def bootstrap_sqlite_schema(url: str = "sqlite+pysqlite:///:memory:") -> Engine:
    engine = create_engine(url, future=True)
    metadata.create_all(engine)
    return engine


class SessionRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def create_campaign(self, campaign_id: str, name: str, payload: dict[str, Any]) -> None:
        with self._engine.begin() as connection:
            connection.execute(
                insert(campaigns).values(
                    id=campaign_id,
                    name=name,
                    payload=payload,
                    created_at=datetime.utcnow(),
                )
            )

    def create_scene(self, scene_id: str, campaign_id: str, name: str, payload: dict[str, Any]) -> None:
        with self._engine.begin() as connection:
            connection.execute(
                insert(scenes).values(
                    id=scene_id,
                    campaign_id=campaign_id,
                    name=name,
                    payload=payload,
                    created_at=datetime.utcnow(),
                )
            )

    def ensure_campaign(self, campaign_id: str, name: str, payload: dict[str, Any]) -> None:
        """Create campaign if it doesn't already exist (idempotent)."""
        with self._engine.begin() as connection:
            exists = connection.execute(
                select(campaigns.c.id).where(campaigns.c.id == campaign_id)
            ).first()
            if not exists:
                connection.execute(
                    insert(campaigns).values(
                        id=campaign_id,
                        name=name,
                        payload=payload,
                        created_at=datetime.utcnow(),
                    )
                )

    def ensure_scene(self, scene_id: str, campaign_id: str, name: str, payload: dict[str, Any]) -> None:
        """Create scene if it doesn't already exist (idempotent)."""
        with self._engine.begin() as connection:
            exists = connection.execute(
                select(scenes.c.id).where(scenes.c.id == scene_id)
            ).first()
            if not exists:
                connection.execute(
                    insert(scenes).values(
                        id=scene_id,
                        campaign_id=campaign_id,
                        name=name,
                        payload=payload,
                        created_at=datetime.utcnow(),
                    )
                )

    def create_session(self, session_payload: dict[str, Any]) -> None:
        session = session_payload["session"]
        with self._engine.begin() as connection:
            connection.execute(
                insert(sessions).values(
                    id=session["session_id"],
                    campaign_id=session["campaign_id"],
                    scene_id=session["scene_id"],
                    status=session["status"],
                    payload=session_payload,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                )
            )

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        with self._engine.connect() as connection:
            row = connection.execute(select(sessions.c.payload).where(sessions.c.id == session_id)).first()
        return None if row is None else row[0]

    def update_session_status(self, session_id: str, status: str, payload: dict[str, Any] | None = None) -> bool:
        from sqlalchemy import update
        with self._engine.begin() as connection:
            values: dict[str, Any] = {"status": status, "updated_at": datetime.utcnow()}
            if payload is not None:
                values["payload"] = payload
            result = connection.execute(
                update(sessions).where(sessions.c.id == session_id).values(**values)
            )
        return result.rowcount > 0

    def list_sessions(
        self,
        *,
        status: str | None = None,
        campaign_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        query = select(
            sessions.c.id,
            sessions.c.campaign_id,
            sessions.c.scene_id,
            sessions.c.status,
            sessions.c.created_at,
            sessions.c.updated_at,
            sessions.c.payload,
        )
        if status is not None:
            query = query.where(sessions.c.status == status)
        if campaign_id is not None:
            query = query.where(sessions.c.campaign_id == campaign_id)
        query = query.order_by(desc(sessions.c.updated_at)).limit(limit).offset(offset)
        with self._engine.connect() as connection:
            rows = connection.execute(query).all()
        return [
            {
                "session_id": row[0],
                "campaign_id": row[1],
                "scene_id": row[2],
                "status": row[3],
                "created_at": row[4].isoformat() if row[4] else None,
                "updated_at": row[5].isoformat() if row[5] else None,
                "payload": row[6],
            }
            for row in rows
        ]

    def session_exists(self, session_id: str) -> bool:
        with self._engine.connect() as connection:
            row = connection.execute(
                select(sessions.c.id).where(sessions.c.id == session_id)
            ).first()
        return row is not None


class EventRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._adapter = TypeAdapter(GameEvent)

    def append(self, event_payload: dict[str, Any]) -> None:
        event = self._adapter.validate_python(event_payload)
        actor_id = getattr(event.payload, "actor_id", None)
        with self._engine.begin() as connection:
            connection.execute(
                insert(events).values(
                    id=event.id,
                    session_id=event.session_id,
                    turn_number=event.turn_number,
                    event_type=event.event_type,
                    actor_id=actor_id,
                    trace_id=event.trace_id,
                    correlation_id=event.correlation_id,
                    payload=event.model_dump(mode="json"),
                    created_at=event.created_at,
                )
            )

    def list_for_session(
        self,
        session_id: str,
        *,
        limit: int = 50,
        event_type: str | None = None,
        actor_id: str | None = None,
    ) -> list[dict[str, Any]]:
        query = select(events.c.payload).where(events.c.session_id == session_id)
        if event_type is not None:
            query = query.where(events.c.event_type == event_type)
        if actor_id is not None:
            query = query.where(events.c.actor_id == actor_id)
        query = query.order_by(events.c.turn_number, events.c.created_at).limit(limit)
        with self._engine.connect() as connection:
            rows = connection.execute(query).all()
        return [row[0] for row in rows]


class MessageRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def append(self, payload: dict[str, Any]) -> None:
        message = TableMessage.model_validate(payload)
        with self._engine.begin() as connection:
            connection.execute(
                insert(messages).values(
                    id=message.id,
                    session_id=message.session_id,
                    scene_id=message.scene_id,
                    sender_id=message.sender_id,
                    channel=message.channel,
                    visibility=message.visibility,
                    recipient_ids=message.recipient_ids,
                    turn_number=message.turn_number,
                    payload=message.model_dump(mode="json"),
                    created_at=message.created_at,
                )
            )

    def list_visible(self, session_id: str, *, recipient_id: str | None = None) -> list[dict[str, Any]]:
        query = select(messages.c.payload).where(messages.c.session_id == session_id)
        with self._engine.connect() as connection:
            rows = connection.execute(query.order_by(messages.c.created_at)).all()
        payloads = [row[0] for row in rows]
        if recipient_id is None:
            return payloads
        return [
            payload
            for payload in payloads
            if payload["visibility"] in {"public", "party", "dm_only"} or recipient_id in payload["recipient_ids"]
        ]


class MemoryEntryRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def append(self, payload: dict[str, Any]) -> None:
        entry = MemoryEntry.model_validate(payload)
        with self._engine.begin() as connection:
            connection.execute(
                insert(memory_entries).values(
                    id=entry.id,
                    session_id=entry.session_id,
                    actor_id=entry.actor_id,
                    memory_type=entry.memory_type,
                    importance=entry.importance,
                    visibility=entry.visibility,
                    tags=entry.tags,
                    payload=entry.model_dump(mode="json"),
                    created_at_turn=entry.created_at_turn,
                )
            )

    def list_for_actor(self, session_id: str, actor_id: str) -> list[dict[str, Any]]:
        query = (
            select(memory_entries.c.payload)
            .where(and_(memory_entries.c.session_id == session_id, memory_entries.c.actor_id == actor_id))
            .order_by(desc(memory_entries.c.importance), memory_entries.c.created_at_turn)
        )
        with self._engine.connect() as connection:
            rows = connection.execute(query).all()
        return [row[0] for row in rows]


class ActionRecordRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def append(self, payload: dict[str, Any]) -> None:
        record = ActionRecord.model_validate(payload)
        with self._engine.begin() as connection:
            connection.execute(
                insert(action_records).values(
                    id=record.id,
                    session_id=record.session_id,
                    actor_id=record.actor_id,
                    turn_number=record.turn_number,
                    action_type=record.action_type,
                    status=record.status,
                    source=record.source,
                    event_id=record.event_id,
                    payload=record.model_dump(mode="json"),
                    created_at=record.created_at,
                )
            )

    def list_for_session(self, session_id: str) -> list[dict[str, Any]]:
        with self._engine.connect() as connection:
            rows = connection.execute(
                select(action_records.c.payload)
                .where(action_records.c.session_id == session_id)
                .order_by(action_records.c.turn_number, action_records.c.created_at)
            ).all()
        return [row[0] for row in rows]


class StateSnapshotRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def append(self, payload: dict[str, Any]) -> None:
        snapshot = StateSnapshotRecord.model_validate(payload)
        with self._engine.begin() as connection:
            connection.execute(
                insert(character_state_snapshots).values(
                    id=snapshot.id,
                    session_id=snapshot.session_id,
                    scene_id=snapshot.scene_id,
                    turn_number=snapshot.turn_number,
                    active_actor_id=snapshot.active_actor_id,
                    payload=snapshot.model_dump(mode="json"),
                    created_at=snapshot.created_at,
                )
            )

    def save_game_state(self, state: GameState, snapshot_id: str | None = None) -> str:
        import uuid
        snap_id = snapshot_id or str(uuid.uuid4())
        now = datetime.utcnow()
        snapshot = StateSnapshotRecord(
            id=snap_id,
            session_id=state.session_id,
            scene_id=state.scene.scene_id,
            turn_number=state.turn.turn_number,
            active_actor_id=state.turn.active_actor_id,
            state=state,
            created_at=now,
        )
        with self._engine.begin() as connection:
            connection.execute(
                insert(character_state_snapshots).values(
                    id=snapshot.id,
                    session_id=snapshot.session_id,
                    scene_id=snapshot.scene_id,
                    turn_number=snapshot.turn_number,
                    active_actor_id=snapshot.active_actor_id,
                    payload=snapshot.model_dump(mode="json"),
                    created_at=snapshot.created_at,
                )
            )
        return snap_id

    def get_latest(self, session_id: str) -> dict[str, Any] | None:
        query = (
            select(character_state_snapshots.c.payload)
            .where(character_state_snapshots.c.session_id == session_id)
            .order_by(desc(character_state_snapshots.c.turn_number), desc(character_state_snapshots.c.created_at))
            .limit(1)
        )
        with self._engine.connect() as connection:
            row = connection.execute(query).first()
        return None if row is None else row[0]

    def get_latest_game_state(self, session_id: str) -> GameState | None:
        payload = self.get_latest(session_id)
        if payload is None:
            return None
        snapshot = StateSnapshotRecord.model_validate(payload)
        return snapshot.state

    def list_snapshots(self, session_id: str, *, limit: int = 20) -> list[dict[str, Any]]:
        query = (
            select(
                character_state_snapshots.c.id,
                character_state_snapshots.c.turn_number,
                character_state_snapshots.c.active_actor_id,
                character_state_snapshots.c.created_at,
            )
            .where(character_state_snapshots.c.session_id == session_id)
            .order_by(desc(character_state_snapshots.c.turn_number), desc(character_state_snapshots.c.created_at))
            .limit(limit)
        )
        with self._engine.connect() as connection:
            rows = connection.execute(query).all()
        return [
            {
                "snapshot_id": row[0],
                "turn_number": row[1],
                "active_actor_id": row[2],
                "created_at": row[3].isoformat() if row[3] else None,
            }
            for row in rows
        ]


class AIInvocationRepository:
    """Repository for storing AI agent invocation records."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def append(self, record: dict[str, Any]) -> None:
        """Store an AI invocation record."""
        with self._engine.begin() as connection:
            connection.execute(
                insert(ai_invocations).values(
                    id=record["id"],
                    session_id=record["session_id"],
                    turn_number=record["turn_number"],
                    phase=record["phase"],
                    actor_id=record["actor_id"],
                    actor_name=record.get("actor_name"),
                    invocation_mode=record.get("invocation_mode"),
                    model=record.get("model"),
                    prompt_tokens=record.get("prompt_tokens"),
                    completion_tokens=record.get("completion_tokens"),
                    latency_ms=record.get("latency_ms"),
                    success=record["success"],
                    error=record.get("error"),
                    response_payload=record["response_payload"],
                    created_at=record["created_at"],
                )
            )

    def list_for_session(
        self,
        session_id: str,
        *,
        limit: int = 100,
        actor_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """List AI invocations for a session."""
        query = select(
            ai_invocations.c.id,
            ai_invocations.c.session_id,
            ai_invocations.c.turn_number,
            ai_invocations.c.phase,
            ai_invocations.c.actor_id,
            ai_invocations.c.actor_name,
            ai_invocations.c.invocation_mode,
            ai_invocations.c.model,
            ai_invocations.c.prompt_tokens,
            ai_invocations.c.completion_tokens,
            ai_invocations.c.latency_ms,
            ai_invocations.c.success,
            ai_invocations.c.error,
            ai_invocations.c.response_payload,
            ai_invocations.c.created_at,
        ).where(ai_invocations.c.session_id == session_id)

        if actor_id is not None:
            query = query.where(ai_invocations.c.actor_id == actor_id)

        query = query.order_by(ai_invocations.c.turn_number, ai_invocations.c.created_at).limit(limit)

        with self._engine.connect() as connection:
            rows = connection.execute(query).all()

        return [
            {
                "id": row[0],
                "session_id": row[1],
                "turn_number": row[2],
                "phase": row[3],
                "actor_id": row[4],
                "actor_name": row[5],
                "invocation_mode": row[6],
                "model": row[7],
                "prompt_tokens": row[8],
                "completion_tokens": row[9],
                "latency_ms": row[10],
                "success": row[11],
                "error": row[12],
                "response_payload": row[13],
                "created_at": row[14].isoformat() if row[14] else None,
            }
            for row in rows
        ]

    def count_for_session(self, session_id: str) -> int:
        """Count AI invocations for a session."""
        from sqlalchemy import func
        query = select(func.count()).select_from(ai_invocations).where(
            ai_invocations.c.session_id == session_id
        )
        with self._engine.connect() as connection:
            result = connection.execute(query).scalar()
        return result or 0
