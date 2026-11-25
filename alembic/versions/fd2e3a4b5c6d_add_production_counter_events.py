"""add durable Edge production-counter events

Revision ID: fd2e3a4b5c6d
Revises: fc1d2e3f4a5b
"""

from alembic import op
import sqlalchemy as sa

revision = "fd2e3a4b5c6d"
down_revision = "fc1d2e3f4a5b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("production_counter_events"):
        # A reporting deployment created this dataset before the Edge API was
        # released.  It already has the required event columns (with wider
        # varchar/integer types), so retain its data and only register this
        # revision.  Do not recreate or alter a live warehouse table here.
        existing = {column["name"] for column in inspector.get_columns("production_counter_events")}
        required = {"id", "tenant_id", "source_event_id", "line_id", "counter_id", "counter_name", "counter_epoch", "observed_at", "quantity", "ok_quantity", "nok_quantity", "delta_quantity", "delta_ok", "delta_nok", "reset_detected", "received_at"}
        missing = required - existing
        if missing:
            raise RuntimeError(f"Existing production_counter_events table is missing: {', '.join(sorted(missing))}")
        return
    op.create_table("production_counter_events",
        sa.Column("id", sa.BigInteger(), primary_key=True), sa.Column("source_event_id", sa.String(64), nullable=False),
        sa.Column("line_id", sa.String(100), nullable=False), sa.Column("counter_id", sa.String(100), nullable=False), sa.Column("counter_name", sa.String(100), nullable=False),
        sa.Column("counter_epoch", sa.Integer(), nullable=False, server_default=sa.text("0")), sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 3), nullable=False), sa.Column("ok_quantity", sa.Numeric(18, 3), nullable=False), sa.Column("nok_quantity", sa.Numeric(18, 3), nullable=False),
        sa.Column("delta_quantity", sa.Numeric(18, 3)), sa.Column("delta_ok", sa.Numeric(18, 3)), sa.Column("delta_nok", sa.Numeric(18, 3)),
        sa.Column("reset_detected", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")), sa.Column("received_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("tenant_id", sa.String(50), sa.ForeignKey("tb_tenants.tenant_id"), nullable=False, server_default=sa.text("'DEFAULT'")),
        sa.CheckConstraint("counter_epoch >= 0", name="ck_production_counter_events_epoch_non_negative"),
        sa.CheckConstraint("quantity >= 0 AND ok_quantity >= 0 AND nok_quantity >= 0", name="ck_production_counter_events_quantities_non_negative"),
        sa.UniqueConstraint("tenant_id", "source_event_id", name="uq_production_counter_events_source_event"),
    )
    op.create_index("ix_production_counter_events_tenant_line_time", "production_counter_events", ["tenant_id", "line_id", "observed_at"])


def downgrade() -> None:
    op.drop_table("production_counter_events")
