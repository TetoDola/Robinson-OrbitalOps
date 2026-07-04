"""Add scenario and telemetry tables for simulator."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "phase2_simulator"
down_revision = "agent_status_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scenario_runs",
        sa.Column("id", sa.String(length=64), primary_key=True, nullable=False),
        sa.Column("scenario_name", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("scenario_runs_status_idx", "scenario_runs", ["status", "started_at"])

    op.create_table(
        "telemetry_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("scenario_run_id", sa.String(length=64), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("asset_id", sa.String(length=64), nullable=True),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("telemetry_events_latest_idx", "telemetry_events", ["event_type", "created_at"])
    op.create_index("telemetry_events_run_idx", "telemetry_events", ["scenario_run_id", "created_at"])


def downgrade() -> None:
    op.drop_index("telemetry_events_run_idx", table_name="telemetry_events")
    op.drop_index("telemetry_events_latest_idx", table_name="telemetry_events")
    op.drop_table("telemetry_events")
    op.drop_index("scenario_runs_status_idx", table_name="scenario_runs")
    op.drop_table("scenario_runs")
