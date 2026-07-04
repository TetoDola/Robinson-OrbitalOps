"""Add first vertical incident and mission patch tables."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "phase3_vertical_slice"
down_revision = "phase2_simulator"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_findings",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("scenario_run_id", sa.String(length=64), nullable=True),
        sa.Column("agent_name", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("confidence", sa.Numeric(), nullable=False),
        sa.Column("affected_assets", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("finding", sa.String(length=512), nullable=False),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("risk", sa.String(length=512), nullable=True),
        sa.Column("recommended_actions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("finding_signature", sa.String(length=128), nullable=False),
        sa.Column("scenario_time_bucket", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "scenario_run_id",
            "agent_name",
            "finding_signature",
            "scenario_time_bucket",
            name="agent_findings_dedupe_idx",
        ),
    )
    op.create_index("agent_findings_open_idx", "agent_findings", ["status", "severity", "created_at"])

    op.create_table(
        "incidents",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("scenario_run_id", sa.String(length=64), nullable=True),
        sa.Column("incident_key", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("finding_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("summary", sa.String(length=1024), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("scenario_run_id", "incident_key", name="incidents_run_key_idx"),
    )

    op.create_table(
        "mission_patches",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("scenario_run_id", sa.String(length=64), nullable=True),
        sa.Column("incident_id", sa.String(length=36), nullable=True),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("summary", sa.String(length=1024), nullable=False),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("actions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("rollback_plan", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("approval_required", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("mission_patches_status_idx", "mission_patches", ["status", "updated_at"])
    op.create_index(
        "mission_patches_one_active_incident",
        "mission_patches",
        ["incident_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('pending_approval', 'approved', 'executing')"),
    )

    op.create_table(
        "commands",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("scenario_run_id", sa.String(length=64), nullable=True),
        sa.Column("mission_patch_id", sa.String(length=36), nullable=False),
        sa.Column("action_type", sa.String(length=64), nullable=False),
        sa.Column("target_asset_id", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("input", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("commands_queue_idx", "commands", ["status", "created_at"])

    op.create_table(
        "approvals",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("scenario_run_id", sa.String(length=64), nullable=True),
        sa.Column("mission_patch_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("operator_id", sa.String(length=64), nullable=True),
        sa.Column("operator_note", sa.String(length=512), nullable=True),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("approvals")
    op.drop_index("commands_queue_idx", table_name="commands")
    op.drop_table("commands")
    op.drop_index("mission_patches_one_active_incident", table_name="mission_patches")
    op.drop_index("mission_patches_status_idx", table_name="mission_patches")
    op.drop_table("mission_patches")
    op.drop_table("incidents")
    op.drop_index("agent_findings_open_idx", table_name="agent_findings")
    op.drop_table("agent_findings")
