"""add central stoppage event dataset

Revision ID: fc1d2e3f4a5b
Revises: fb8c9d0e1f2a
"""

from alembic import op
import sqlalchemy as sa


revision = "fc1d2e3f4a5b"
down_revision = "fb8c9d0e1f2a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stoppage_events",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("source_event_id", sa.String(64), nullable=False),
        sa.Column("line_id", sa.String(100), nullable=False),
        sa.Column("station_id", sa.String(100), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Numeric(14, 3), nullable=True),
        sa.Column("reason", sa.String(40), nullable=False),
        sa.Column("source_state", sa.String(40), nullable=False),
        sa.Column("shift", sa.String(10), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 3), nullable=False),
        sa.Column("edge_updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("tenant_id", sa.String(50), sa.ForeignKey("tb_tenants.tenant_id"), nullable=False, server_default=sa.text("'DEFAULT'")),
        sa.CheckConstraint("duration_seconds IS NULL OR duration_seconds >= 0", name="ck_stoppage_events_duration_non_negative"),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_stoppage_events_confidence_range"),
        sa.UniqueConstraint("tenant_id", "source_event_id", name="uq_stoppage_events_source_event"),
    )
    op.create_index("ix_stoppage_events_tenant_line_started", "stoppage_events", ["tenant_id", "line_id", "started_at"])
    op.create_index("ix_stoppage_events_tenant_station_started", "stoppage_events", ["tenant_id", "station_id", "started_at"])
    op.create_index("ix_stoppage_events_tenant_reason_started", "stoppage_events", ["tenant_id", "reason", "started_at"])


def downgrade() -> None:
    op.drop_table("stoppage_events")
