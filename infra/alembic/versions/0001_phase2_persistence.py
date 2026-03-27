"""Initial persistence and infrastructure schema."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0001_phase2_persistence"
down_revision = None
branch_labels = None
depends_on = None


def _payload_type() -> sa.types.TypeEngine:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        from sqlalchemy.dialects import postgresql

        return postgresql.JSONB(astext_type=sa.Text())
    return sa.JSON()


def upgrade() -> None:
    payload_type = _payload_type()

    op.create_table(
        "campaigns",
        sa.Column("id", sa.String(length=255), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("payload", payload_type, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "scenes",
        sa.Column("id", sa.String(length=255), primary_key=True),
        sa.Column("campaign_id", sa.String(length=255), sa.ForeignKey("campaigns.id"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("payload", payload_type, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_scenes_campaign_id", "scenes", ["campaign_id"])
    op.create_table(
        "sessions",
        sa.Column("id", sa.String(length=255), primary_key=True),
        sa.Column("campaign_id", sa.String(length=255), sa.ForeignKey("campaigns.id"), nullable=False),
        sa.Column("scene_id", sa.String(length=255), sa.ForeignKey("scenes.id"), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("payload", payload_type, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_sessions_campaign_id", "sessions", ["campaign_id"])
    op.create_index("ix_sessions_scene_id", "sessions", ["scene_id"])
    op.create_index("ix_sessions_status", "sessions", ["status"])
    op.create_table(
        "actors",
        sa.Column("id", sa.String(length=255), primary_key=True),
        sa.Column("session_id", sa.String(length=255), sa.ForeignKey("sessions.id"), nullable=False),
        sa.Column("scene_id", sa.String(length=255), sa.ForeignKey("scenes.id"), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("payload", payload_type, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_actors_session_id", "actors", ["session_id"])
    op.create_index("ix_actors_scene_id", "actors", ["scene_id"])
    op.create_index("ix_actors_role", "actors", ["role"])
    op.create_table(
        "character_state_snapshots",
        sa.Column("id", sa.String(length=255), primary_key=True),
        sa.Column("session_id", sa.String(length=255), sa.ForeignKey("sessions.id"), nullable=False),
        sa.Column("scene_id", sa.String(length=255), sa.ForeignKey("scenes.id"), nullable=False),
        sa.Column("turn_number", sa.Integer(), nullable=False),
        sa.Column("active_actor_id", sa.String(length=255), nullable=True),
        sa.Column("payload", payload_type, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_snapshots_session_turn", "character_state_snapshots", ["session_id", "turn_number"])
    op.create_table(
        "events",
        sa.Column("id", sa.String(length=255), primary_key=True),
        sa.Column("session_id", sa.String(length=255), sa.ForeignKey("sessions.id"), nullable=False),
        sa.Column("turn_number", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("actor_id", sa.String(length=255), nullable=True),
        sa.Column("trace_id", sa.String(length=255), nullable=False),
        sa.Column("correlation_id", sa.String(length=255), nullable=False),
        sa.Column("payload", payload_type, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_events_session_created_at", "events", ["session_id", "created_at"])
    op.create_index("ix_events_session_turn", "events", ["session_id", "turn_number"])
    op.create_index("ix_events_session_event_type", "events", ["session_id", "event_type"])
    op.create_index("ix_events_session_actor_id", "events", ["session_id", "actor_id"])
    op.create_table(
        "messages",
        sa.Column("id", sa.String(length=255), primary_key=True),
        sa.Column("session_id", sa.String(length=255), sa.ForeignKey("sessions.id"), nullable=False),
        sa.Column("scene_id", sa.String(length=255), sa.ForeignKey("scenes.id"), nullable=False),
        sa.Column("sender_id", sa.String(length=255), nullable=False),
        sa.Column("channel", sa.String(length=50), nullable=False),
        sa.Column("visibility", sa.String(length=50), nullable=False),
        sa.Column("recipient_ids", payload_type, nullable=False),
        sa.Column("turn_number", sa.Integer(), nullable=False),
        sa.Column("payload", payload_type, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_messages_session_created_at", "messages", ["session_id", "created_at"])
    op.create_index("ix_messages_session_visibility", "messages", ["session_id", "visibility"])
    op.create_index("ix_messages_session_channel", "messages", ["session_id", "channel"])
    op.create_table(
        "memory_entries",
        sa.Column("id", sa.String(length=255), primary_key=True),
        sa.Column("session_id", sa.String(length=255), sa.ForeignKey("sessions.id"), nullable=False),
        sa.Column("actor_id", sa.String(length=255), nullable=False),
        sa.Column("memory_type", sa.String(length=50), nullable=False),
        sa.Column("importance", sa.Integer(), nullable=False),
        sa.Column("visibility", sa.String(length=50), nullable=False),
        sa.Column("tags", payload_type, nullable=False),
        sa.Column("payload", payload_type, nullable=False),
        sa.Column("created_at_turn", sa.Integer(), nullable=False),
    )
    op.create_index("ix_memory_session_actor", "memory_entries", ["session_id", "actor_id"])
    op.create_index("ix_memory_session_importance", "memory_entries", ["session_id", "importance"])
    op.create_table(
        "action_records",
        sa.Column("id", sa.String(length=255), primary_key=True),
        sa.Column("session_id", sa.String(length=255), sa.ForeignKey("sessions.id"), nullable=False),
        sa.Column("actor_id", sa.String(length=255), nullable=False),
        sa.Column("turn_number", sa.Integer(), nullable=False),
        sa.Column("action_type", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("event_id", sa.String(length=255), nullable=True),
        sa.Column("payload", payload_type, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_actions_session_turn", "action_records", ["session_id", "turn_number"])
    op.create_index("ix_actions_session_actor", "action_records", ["session_id", "actor_id"])


def downgrade() -> None:
    op.drop_index("ix_actions_session_actor", table_name="action_records")
    op.drop_index("ix_actions_session_turn", table_name="action_records")
    op.drop_table("action_records")
    op.drop_index("ix_memory_session_importance", table_name="memory_entries")
    op.drop_index("ix_memory_session_actor", table_name="memory_entries")
    op.drop_table("memory_entries")
    op.drop_index("ix_messages_session_channel", table_name="messages")
    op.drop_index("ix_messages_session_visibility", table_name="messages")
    op.drop_index("ix_messages_session_created_at", table_name="messages")
    op.drop_table("messages")
    op.drop_index("ix_events_session_actor_id", table_name="events")
    op.drop_index("ix_events_session_event_type", table_name="events")
    op.drop_index("ix_events_session_turn", table_name="events")
    op.drop_index("ix_events_session_created_at", table_name="events")
    op.drop_table("events")
    op.drop_index("ix_snapshots_session_turn", table_name="character_state_snapshots")
    op.drop_table("character_state_snapshots")
    op.drop_index("ix_actors_role", table_name="actors")
    op.drop_index("ix_actors_scene_id", table_name="actors")
    op.drop_index("ix_actors_session_id", table_name="actors")
    op.drop_table("actors")
    op.drop_index("ix_sessions_status", table_name="sessions")
    op.drop_index("ix_sessions_scene_id", table_name="sessions")
    op.drop_index("ix_sessions_campaign_id", table_name="sessions")
    op.drop_table("sessions")
    op.drop_index("ix_scenes_campaign_id", table_name="scenes")
    op.drop_table("scenes")
    op.drop_table("campaigns")
