"""Add AI invocations table for tracking agent responses."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0002_ai_invocations"
down_revision = "0001_phase2_persistence"
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
        "ai_invocations",
        sa.Column("id", sa.String(length=255), primary_key=True),
        sa.Column("session_id", sa.String(length=255), sa.ForeignKey("sessions.id"), nullable=False),
        sa.Column("turn_number", sa.Integer(), nullable=False),
        sa.Column("phase", sa.String(length=50), nullable=False),
        sa.Column("actor_id", sa.String(length=255), nullable=False),
        sa.Column("actor_name", sa.String(length=255), nullable=True),
        sa.Column("invocation_mode", sa.String(length=50), nullable=True),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("response_payload", payload_type, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ai_invocations_session_id", "ai_invocations", ["session_id"])
    op.create_index("ix_ai_invocations_session_turn", "ai_invocations", ["session_id", "turn_number"])
    op.create_index("ix_ai_invocations_session_actor", "ai_invocations", ["session_id", "actor_id"])
    op.create_index("ix_ai_invocations_created_at", "ai_invocations", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_ai_invocations_created_at", table_name="ai_invocations")
    op.drop_index("ix_ai_invocations_session_actor", table_name="ai_invocations")
    op.drop_index("ix_ai_invocations_session_turn", table_name="ai_invocations")
    op.drop_index("ix_ai_invocations_session_id", table_name="ai_invocations")
    op.drop_table("ai_invocations")
