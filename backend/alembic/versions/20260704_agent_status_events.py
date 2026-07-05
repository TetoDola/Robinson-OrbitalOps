"""Add append-only agent status event log."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "agent_status_events"
down_revision = "phase1_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_status_events",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("scenario_run_id", sa.String(length=64), nullable=True),
        sa.Column("agent_name", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("phase", sa.String(length=32), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("message", sa.String(length=512), nullable=False),
        sa.Column("current_task", sa.String(length=255), nullable=True),
        sa.Column("progress", sa.Numeric(), nullable=True),
        sa.Column(
            "affected_assets",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("linked_finding_id", sa.String(length=64), nullable=True),
        sa.Column("linked_incident_id", sa.String(length=64), nullable=True),
        sa.Column("linked_mission_patch_id", sa.String(length=64), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "agent_status_events_latest_idx",
        "agent_status_events",
        ["agent_name", "created_at"],
    )
    op.create_index(
        "agent_status_events_run_idx",
        "agent_status_events",
        ["scenario_run_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("agent_status_events_run_idx", table_name="agent_status_events")
    op.drop_index("agent_status_events_latest_idx", table_name="agent_status_events")
    op.drop_table("agent_status_events")
