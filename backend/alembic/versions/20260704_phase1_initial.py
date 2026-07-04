"""Initial schema and seed-table support for Phase 1."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "phase1_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "world_state_current",
        sa.Column("id", sa.Boolean(), primary_key=True, nullable=False, server_default=sa.text("true")),
        sa.Column("scenario_run_id", sa.String(length=64), nullable=True),
        sa.Column("version", sa.BigInteger(), nullable=False),
        sa.Column("state", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("updated_by", sa.String(length=64), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("id IS TRUE", name="world_state_current_id_is_true"),
    )

    op.create_table(
        "world_state_snapshots",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("scenario_run_id", sa.String(length=64), nullable=True),
        sa.Column("version", sa.BigInteger(), nullable=False),
        sa.Column("state", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("scenario_run_id", "version", name="uq_world_state_snapshot_run_version"),
    )

    op.create_table(
        "agent_statuses",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("agent", sa.String(length=64), nullable=False, unique=True),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("phase", sa.String(length=32), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("message", sa.String(length=512), nullable=False),
        sa.Column("linked_mission_patch_id", sa.String(length=64), nullable=True),
        sa.Column("updated_by", sa.String(length=64), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("agent_statuses")
    op.drop_table("world_state_snapshots")
    op.drop_table("world_state_current")
