from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Integer,
    JSON,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class TbLines(Base):
    __tablename__ = "tb_lines"

    id_row: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    line_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    description_line: Mapped[str] = mapped_column(String(50), nullable=False)
    plant_id: Mapped[str | None] = mapped_column(String(50), ForeignKey("tb_plants.plant_id"))
    tenant_id: Mapped[str] = mapped_column(String(50), ForeignKey("tb_tenants.tenant_id"), nullable=False, server_default=text("'DEFAULT'"))
    create_date: Mapped[datetime] = mapped_column(DateTime, server_default=text("CURRENT_TIMESTAMP"), nullable=False)


class TbPlants(Base):
    __tablename__ = "tb_plants"

    id_row: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    plant_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    description_plant: Mapped[str] = mapped_column(String(100), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(50), ForeignKey("tb_tenants.tenant_id"), nullable=False, server_default=text("'DEFAULT'"))
    create_date: Mapped[datetime] = mapped_column(DateTime, server_default=text("CURRENT_TIMESTAMP"), nullable=False)


class TbTenants(Base):
    __tablename__ = "tb_tenants"

    id_row: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name_tenant: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("TRUE"), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, server_default=text("FALSE"), nullable=False)
    create_date: Mapped[datetime] = mapped_column(DateTime, server_default=text("CURRENT_TIMESTAMP"), nullable=False)


class TbPortalSettings(Base):
    __tablename__ = "tb_portal_settings"

    id_row: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(50), ForeignKey("tb_tenants.tenant_id"), unique=True, nullable=False)
    portal_title: Mapped[str] = mapped_column(String(100), nullable=False, server_default=text("'RupMes'"))
    logo_image: Mapped[str | None] = mapped_column(Text)
    create_date: Mapped[datetime] = mapped_column(DateTime, server_default=text("CURRENT_TIMESTAMP"), nullable=False)
    update_date: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=text("CURRENT_TIMESTAMP"),
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint("trim(portal_title) <> ''", name="ck_tb_portal_settings_title_not_blank"),
        Index("ix_tb_portal_settings_tenant_id", "tenant_id"),
    )


class TbRoles(Base):
    __tablename__ = "tb_roles"

    id_row: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    role_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    description_role: Mapped[str] = mapped_column(String(100), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(50), ForeignKey("tb_tenants.tenant_id"), nullable=False)
    create_date: Mapped[datetime] = mapped_column(DateTime, server_default=text("CURRENT_TIMESTAMP"), nullable=False)

    __table_args__ = (
        Index("ix_tb_roles_tenant_id", "tenant_id"),
    )


class TbPermissions(Base):
    __tablename__ = "tb_permissions"

    id_row: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    permission_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description_permission: Mapped[str] = mapped_column(String(150), nullable=False)


class TbRolePermissions(Base):
    __tablename__ = "tb_role_permissions"

    id_row: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    role_id: Mapped[str] = mapped_column(String(50), ForeignKey("tb_roles.role_id"), nullable=False)
    permission_id: Mapped[str] = mapped_column(String(100), ForeignKey("tb_permissions.permission_id"), nullable=False)

    __table_args__ = (
        UniqueConstraint("role_id", "permission_id", name="uq_role_permission"),
        Index("ix_tb_role_permissions_role_id", "role_id"),
        Index("ix_tb_role_permissions_permission_id", "permission_id"),
    )


class TbUserRoles(Base):
    __tablename__ = "tb_user_roles"

    id_row: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    id_user: Mapped[str] = mapped_column(String(50), ForeignKey("tb_users.id_user"), nullable=False)
    role_id: Mapped[str] = mapped_column(String(50), ForeignKey("tb_roles.role_id"), nullable=False)

    __table_args__ = (
        UniqueConstraint("id_user", "role_id", name="uq_user_role"),
        Index("ix_tb_user_roles_id_user", "id_user"),
        Index("ix_tb_user_roles_role_id", "role_id"),
    )


class TbUserTenants(Base):
    __tablename__ = "tb_user_tenants"

    id_row: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    id_user: Mapped[str] = mapped_column(String(50), ForeignKey("tb_users.id_user"), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(50), ForeignKey("tb_tenants.tenant_id"), nullable=False)

    __table_args__ = (
        UniqueConstraint("id_user", "tenant_id", name="uq_user_tenant"),
        Index("ix_tb_user_tenants_id_user", "id_user"),
        Index("ix_tb_user_tenants_tenant_id", "tenant_id"),
    )


class TbSessions(Base):
    __tablename__ = "tb_sessions"

    id_row: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    id_user: Mapped[str] = mapped_column(String(50), ForeignKey("tb_users.id_user"), nullable=False)
    csrf_token: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=text("CURRENT_TIMESTAMP"), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, server_default=text("CURRENT_TIMESTAMP"), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(String(200))

    __table_args__ = (
        Index("ix_tb_sessions_id_user", "id_user"),
        Index("ix_tb_sessions_expires_at", "expires_at"),
    )


class TbCells(Base):
    __tablename__ = "tb_cells"

    id_row: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    cell_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    description_cell: Mapped[str] = mapped_column(String(50), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(50), ForeignKey("tb_tenants.tenant_id"), nullable=False, server_default=text("'DEFAULT'"))
    create_date: Mapped[datetime] = mapped_column(DateTime, server_default=text("CURRENT_TIMESTAMP"), nullable=False)


class TbRoutings(Base):
    __tablename__ = "tb_routings"

    id_row: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    routing_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    description_routing: Mapped[str] = mapped_column(String(50), nullable=False)
    line_id: Mapped[str | None] = mapped_column(String(50), ForeignKey("tb_lines.line_id"))
    tenant_id: Mapped[str] = mapped_column(String(50), ForeignKey("tb_tenants.tenant_id"), nullable=False, server_default=text("'DEFAULT'"))
    create_date: Mapped[datetime] = mapped_column(DateTime, server_default=text("CURRENT_TIMESTAMP"), nullable=False)


class TbModels(Base):
    __tablename__ = "tb_models"

    id_row: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    model_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    description_model: Mapped[str] = mapped_column(String(50), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(50), ForeignKey("tb_tenants.tenant_id"), nullable=False, server_default=text("'DEFAULT'"))
    create_date: Mapped[datetime] = mapped_column(DateTime, server_default=text("CURRENT_TIMESTAMP"), nullable=False)


class TbStatus(Base):
    __tablename__ = "tb_status"

    id_row: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    status_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    description_status: Mapped[str] = mapped_column(String(50), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(50), ForeignKey("tb_tenants.tenant_id"), nullable=False, server_default=text("'DEFAULT'"))


class TbGroups(Base):
    __tablename__ = "tb_groups"

    id_row: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    id_group: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)
    name_group: Mapped[str] = mapped_column(String(50), nullable=False)
    level_group: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    create_date: Mapped[datetime] = mapped_column(DateTime, server_default=text("CURRENT_TIMESTAMP"), nullable=False)


class TbUserStatus(Base):
    __tablename__ = "tb_user_status"

    id_row: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    status_user: Mapped[str] = mapped_column(String(3), unique=True, nullable=False)
    description_status: Mapped[str] = mapped_column(String(50), nullable=False)
    create_date: Mapped[datetime] = mapped_column(DateTime, server_default=text("CURRENT_TIMESTAMP"), nullable=False)


class TbUsers(Base):
    __tablename__ = "tb_users"

    id_row: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    id_user: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name_user: Mapped[str] = mapped_column(String(50), nullable=False)
    mail_user: Mapped[str] = mapped_column(String(50), nullable=False)
    tenant_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("tb_tenants.tenant_id"),
        nullable=False,
        server_default=text("'DEFAULT'"),
    )
    id_group: Mapped[str] = mapped_column(String(10), ForeignKey("tb_groups.id_group"), nullable=False)
    status_user: Mapped[str] = mapped_column(String(3), ForeignKey("tb_user_status.status_user"), nullable=False)
    pass_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    create_date: Mapped[datetime] = mapped_column(DateTime, server_default=text("CURRENT_TIMESTAMP"), nullable=False)


class TbItems(Base):
    __tablename__ = "tb_items"

    id_row: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    item_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    model_id: Mapped[str] = mapped_column(String(50), ForeignKey("tb_models.model_id"), nullable=False)
    line_id: Mapped[str] = mapped_column(String(50), ForeignKey("tb_lines.line_id"), nullable=False)
    location_id: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    cell_id: Mapped[str] = mapped_column(String(50), ForeignKey("tb_cells.cell_id"), nullable=False)
    id_user: Mapped[str] = mapped_column(String(50), ForeignKey("tb_users.id_user"), nullable=False)
    create_date: Mapped[datetime] = mapped_column(DateTime, server_default=text("CURRENT_TIMESTAMP"), nullable=False)
    last_test_date: Mapped[datetime] = mapped_column(DateTime, server_default=text("CURRENT_TIMESTAMP"), nullable=False)
    status_id: Mapped[str] = mapped_column(String(50), ForeignKey("tb_status.status_id"), nullable=False)
    value1_int: Mapped[int | None] = mapped_column(Integer)
    value2_int: Mapped[int | None] = mapped_column(Integer)
    value3_int: Mapped[int | None] = mapped_column(Integer)
    value4_int: Mapped[int | None] = mapped_column(Integer)
    value5_int: Mapped[int | None] = mapped_column(Integer)
    value1_str: Mapped[str | None] = mapped_column(String(50))
    value2_str: Mapped[str | None] = mapped_column(String(50))
    value3_str: Mapped[str | None] = mapped_column(String(50))
    value4_str: Mapped[str | None] = mapped_column(String(50))
    value5_str: Mapped[str | None] = mapped_column(String(50))
    tenant_id: Mapped[str] = mapped_column(String(50), ForeignKey("tb_tenants.tenant_id"), nullable=False, server_default=text("'DEFAULT'"))

    __table_args__ = (
        Index("ix_tb_items_model_id", "model_id"),
        Index("ix_tb_items_line_id", "line_id"),
        Index("ix_tb_items_status_id", "status_id"),
        Index("ix_tb_items_cell_id", "cell_id"),
        Index("ix_tb_items_id_user", "id_user"),
        Index("ix_tb_items_location_id", "location_id"),
    )


class HisProcItem(Base):
    __tablename__ = "his_proc_item"

    id_row: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    item_id: Mapped[str] = mapped_column(String(50), nullable=False)
    model_id: Mapped[str] = mapped_column(String(50), ForeignKey("tb_models.model_id"), nullable=False)
    line_id: Mapped[str] = mapped_column(String(50), ForeignKey("tb_lines.line_id"), nullable=False)
    location_id: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    cell_id: Mapped[str] = mapped_column(String(50), ForeignKey("tb_cells.cell_id"), nullable=False)
    id_user: Mapped[str] = mapped_column(String(50), ForeignKey("tb_users.id_user"), nullable=False)
    create_date: Mapped[datetime] = mapped_column(DateTime, server_default=text("CURRENT_TIMESTAMP"), nullable=False)
    last_test_date: Mapped[datetime] = mapped_column(DateTime, server_default=text("CURRENT_TIMESTAMP"), nullable=False)
    status_id: Mapped[str] = mapped_column(String(50), ForeignKey("tb_status.status_id"), nullable=False)
    value1_int: Mapped[int | None] = mapped_column(Integer)
    value2_int: Mapped[int | None] = mapped_column(Integer)
    value3_int: Mapped[int | None] = mapped_column(Integer)
    value4_int: Mapped[int | None] = mapped_column(Integer)
    value5_int: Mapped[int | None] = mapped_column(Integer)
    value1_str: Mapped[str | None] = mapped_column(String(50))
    value2_str: Mapped[str | None] = mapped_column(String(50))
    value3_str: Mapped[str | None] = mapped_column(String(50))
    value4_str: Mapped[str | None] = mapped_column(String(50))
    value5_str: Mapped[str | None] = mapped_column(String(50))

    __table_args__ = (
        Index("ix_his_proc_item_item_id", "item_id"),
        Index("ix_his_proc_item_create_date", "create_date"),
    )


class HrefCellLine(Base):
    __tablename__ = "href_cell_line"

    id_row: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    cell_id: Mapped[str] = mapped_column(String(50), ForeignKey("tb_cells.cell_id"), nullable=False)
    line_id: Mapped[str] = mapped_column(String(50), ForeignKey("tb_lines.line_id"), nullable=False)
    create_date: Mapped[datetime] = mapped_column(DateTime, server_default=text("CURRENT_TIMESTAMP"), nullable=False)

    __table_args__ = (
        UniqueConstraint("cell_id", "line_id", name="uq_href_cell_line_cell_line"),
        Index("ix_href_cell_line_cell_id", "cell_id"),
        Index("ix_href_cell_line_line_id", "line_id"),
    )


class HrefRoutingCell(Base):
    __tablename__ = "href_routing_cell"

    id_row: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    routing_id: Mapped[str] = mapped_column(String(50), ForeignKey("tb_routings.routing_id"), nullable=False)
    cell_id: Mapped[str] = mapped_column(String(50), ForeignKey("tb_cells.cell_id"), nullable=False)
    location_id: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    create_date: Mapped[datetime] = mapped_column(DateTime, server_default=text("CURRENT_TIMESTAMP"), nullable=False)

    __table_args__ = (
        UniqueConstraint("routing_id", "cell_id", "location_id", name="uq_href_routing_cell_route_cell_loc"),
        Index("ix_href_routing_cell_routing_id", "routing_id"),
        Index("ix_href_routing_cell_cell_id", "cell_id"),
    )


class HrefRoutingModel(Base):
    __tablename__ = "href_routing_model"

    id_row: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    routing_id: Mapped[str] = mapped_column(String(50), ForeignKey("tb_routings.routing_id"), nullable=False)
    model_id: Mapped[str] = mapped_column(String(50), ForeignKey("tb_models.model_id"), nullable=False)
    location_id: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    __table_args__ = (
        UniqueConstraint("routing_id", "model_id", "location_id", name="uq_href_routing_model_route_model_loc"),
        Index("ix_href_routing_model_routing_id", "routing_id"),
        Index("ix_href_routing_model_model_id", "model_id"),
    )


class RoutingProcess(Base):
    """A sequenced operation in a routing and its tenant-specific result schema."""

    __tablename__ = "routing_processes"

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), Identity(), primary_key=True)
    routing_id: Mapped[str] = mapped_column(String(50), ForeignKey("tb_routings.routing_id", ondelete="CASCADE"), nullable=False)
    process_id: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(String(150), nullable=False)
    cell_id: Mapped[str] = mapped_column(String(50), ForeignKey("tb_cells.cell_id"), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    is_required: Mapped[bool] = mapped_column(Boolean, server_default=text("TRUE"), nullable=False)
    result_schema: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    tenant_id: Mapped[str] = mapped_column(String(50), ForeignKey("tb_tenants.tenant_id"), nullable=False)
    create_date: Mapped[datetime] = mapped_column(DateTime, server_default=text("CURRENT_TIMESTAMP"), nullable=False)

    __table_args__ = (
        CheckConstraint("sequence > 0", name="ck_routing_process_sequence_positive"),
        UniqueConstraint("tenant_id", "routing_id", "process_id", name="uq_routing_process_tenant_route_process"),
        UniqueConstraint("tenant_id", "routing_id", "sequence", name="uq_routing_process_tenant_route_sequence"),
        Index("ix_routing_process_tenant_route", "tenant_id", "routing_id"),
    )


class RoutingModel(Base):
    """Assigns an existing model master to the routing it must follow."""

    __tablename__ = "routing_models"

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), Identity(), primary_key=True)
    model_id: Mapped[str] = mapped_column(String(50), ForeignKey("tb_models.model_id"), nullable=False)
    routing_id: Mapped[str] = mapped_column(String(50), ForeignKey("tb_routings.routing_id", ondelete="CASCADE"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("TRUE"), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(50), ForeignKey("tb_tenants.tenant_id"), nullable=False)
    create_date: Mapped[datetime] = mapped_column(DateTime, server_default=text("CURRENT_TIMESTAMP"), nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "model_id", name="uq_routing_model_tenant_model"),
        Index("ix_routing_model_tenant_routing", "tenant_id", "routing_id"),
    )


class RoutingProcessResult(Base):
    """Immutable traceability evidence generated by one routing process execution."""

    __tablename__ = "routing_process_results"

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), Identity(), primary_key=True)
    model_id: Mapped[str] = mapped_column(String(50), nullable=False)
    serial_number: Mapped[str] = mapped_column(String(150), nullable=False)
    routing_id: Mapped[str] = mapped_column(String(50), nullable=False)
    process_id: Mapped[str] = mapped_column(String(50), nullable=False)
    cell_id: Mapped[str] = mapped_column(String(50), nullable=False)
    result: Mapped[str] = mapped_column(String(20), nullable=False)
    result_values: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    result_schema: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    process_datetime: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    source_system: Mapped[str | None] = mapped_column(String(100))
    tenant_id: Mapped[str] = mapped_column(String(50), ForeignKey("tb_tenants.tenant_id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=text("CURRENT_TIMESTAMP"), nullable=False)

    __table_args__ = (
        CheckConstraint("result IN ('OK', 'NOK', 'SKIPPED')", name="ck_routing_process_result_result"),
        CheckConstraint("trim(serial_number) <> ''", name="ck_routing_process_result_serial_not_blank"),
        Index("ix_routing_process_result_tenant_serial", "tenant_id", "serial_number"),
        Index("ix_routing_process_result_tenant_model", "tenant_id", "model_id"),
        Index("ix_routing_process_result_tenant_route_process", "tenant_id", "routing_id", "process_id"),
    )


class TraceabilityMeasurement(Base):
    """Report-ready values extracted atomically from a routing process result."""

    __tablename__ = "traceability_measurements"

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), Identity(), primary_key=True)
    event_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("routing_process_results.id", ondelete="CASCADE"), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(50), ForeignKey("tb_tenants.tenant_id"), nullable=False)
    serial_number: Mapped[str] = mapped_column(String(150), nullable=False)
    model_id: Mapped[str] = mapped_column(String(50), nullable=False)
    routing_id: Mapped[str] = mapped_column(String(50), nullable=False)
    process_id: Mapped[str] = mapped_column(String(50), nullable=False)
    cell_id: Mapped[str] = mapped_column(String(50), nullable=False)
    result: Mapped[str] = mapped_column(String(20), nullable=False)
    measurement_code: Mapped[str] = mapped_column(String(50), nullable=False)
    measurement_type: Mapped[str] = mapped_column(String(20), nullable=False)
    numeric_value: Mapped[float | None] = mapped_column(Numeric(18, 6))
    text_value: Mapped[str | None] = mapped_column(Text)
    boolean_value: Mapped[bool | None] = mapped_column(Boolean)
    datetime_value: Mapped[datetime | None] = mapped_column(DateTime)
    unit: Mapped[str | None] = mapped_column(String(30))
    process_datetime: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=text("CURRENT_TIMESTAMP"), nullable=False)

    __table_args__ = (
        UniqueConstraint("event_id", "measurement_code", name="uq_traceability_measurement_event_code"),
        Index("ix_traceability_measurement_tenant_process_code", "tenant_id", "process_id", "measurement_code"),
        Index("ix_traceability_measurement_tenant_serial", "tenant_id", "serial_number"),
        Index("ix_traceability_measurement_tenant_datetime", "tenant_id", "process_datetime"),
    )


class ProductionReport(Base):
    __tablename__ = "production_report"

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), Identity(), primary_key=True)
    plant_code: Mapped[str | None] = mapped_column(String(50))
    line_code: Mapped[str] = mapped_column(String(50), nullable=False)
    station_code: Mapped[str | None] = mapped_column(String(50))
    machine_code: Mapped[str | None] = mapped_column(String(50))
    shift_code: Mapped[str | None] = mapped_column(String(20))
    production_order: Mapped[str | None] = mapped_column(String(100))
    product_code: Mapped[str | None] = mapped_column(String(100))
    product_family: Mapped[str | None] = mapped_column(String(100))
    customer: Mapped[str | None] = mapped_column(String(100))
    report_type: Mapped[str] = mapped_column(String(20), server_default=text("'FINISHED_PART'"), nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(18, 3), server_default=text("1"), nullable=False)
    unit_of_measure: Mapped[str] = mapped_column(String(20), server_default=text("'EA'"), nullable=False)
    serial_number: Mapped[str | None] = mapped_column(String(150))
    container_serial: Mapped[str | None] = mapped_column(String(150))
    material_lot: Mapped[str | None] = mapped_column(String(100))
    source_event_id: Mapped[str | None] = mapped_column(String(150))
    result: Mapped[str] = mapped_column(String(20), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(50))
    error_description: Mapped[str | None] = mapped_column(Text)
    defect_station: Mapped[str | None] = mapped_column(String(50))
    production_datetime: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    cycle_time_seconds: Mapped[float | None] = mapped_column(Numeric(10, 3))
    target_cycle_time_seconds: Mapped[float | None] = mapped_column(Numeric(10, 3))
    component_serial: Mapped[str | None] = mapped_column(String(150))
    component_lot: Mapped[str | None] = mapped_column(String(100))
    supplier_code: Mapped[str | None] = mapped_column(String(100))
    nest_number: Mapped[int | None] = mapped_column(Integer)
    tool_id: Mapped[str | None] = mapped_column(String(100))
    program_name: Mapped[str | None] = mapped_column(String(100))
    software_version: Mapped[str | None] = mapped_column(String(100))
    is_rework: Mapped[bool] = mapped_column(Boolean, server_default=text("FALSE"), nullable=False)
    rework_result: Mapped[str | None] = mapped_column(String(20))
    rework_datetime: Mapped[datetime | None] = mapped_column(DateTime)
    source_system: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=text("CURRENT_TIMESTAMP"), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(50), ForeignKey("tb_tenants.tenant_id"), nullable=False, server_default=text("'DEFAULT'"))

    __table_args__ = (
        CheckConstraint("report_type IN ('WIP', 'FINISHED_PART', 'FINISHED_BOX')", name="ck_production_report_type"),
        CheckConstraint("quantity > 0", name="ck_production_report_quantity_positive"),
        CheckConstraint("result IN ('OK', 'NOK', 'SCRAP', 'REWORK')", name="ck_production_report_result"),
        CheckConstraint(
            "rework_result IS NULL OR rework_result IN ('OK', 'NOK', 'SCRAP', 'REWORK')",
            name="ck_production_report_rework_result",
        ),
        CheckConstraint("trim(serial_number) <> ''", name="ck_production_report_serial_not_blank"),
        CheckConstraint("trim(line_code) <> ''", name="ck_production_report_line_not_blank"),
        Index("ix_production_report_production_datetime", "production_datetime"),
        Index("ix_production_report_serial_number", "serial_number"),
        Index("ix_production_report_container_serial", "container_serial"),
        UniqueConstraint("tenant_id", "source_system", "source_event_id", name="uq_production_report_source_event"),
        Index("ix_production_report_line_datetime", "line_code", "production_datetime"),
        Index("ix_production_report_result", "result"),
        Index("ix_production_report_error_code", "error_code"),
    )


class StoppageEvent(Base):
    """An idempotently-ingested, classified downtime event from an Edge."""

    __tablename__ = "stoppage_events"

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), Identity(), primary_key=True)
    source_event_id: Mapped[str] = mapped_column(String(64), nullable=False)
    line_id: Mapped[str] = mapped_column(String(100), nullable=False)
    station_id: Mapped[str] = mapped_column(String(100), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[float | None] = mapped_column(Numeric(14, 3))
    reason: Mapped[str] = mapped_column(String(40), nullable=False)
    source_state: Mapped[str] = mapped_column(String(40), nullable=False)
    shift: Mapped[str] = mapped_column(String(10), nullable=False)
    confidence: Mapped[float] = mapped_column(Numeric(5, 3), nullable=False)
    edge_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("CURRENT_TIMESTAMP"), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(50), ForeignKey("tb_tenants.tenant_id"), nullable=False, server_default=text("'DEFAULT'"))

    __table_args__ = (
        CheckConstraint("duration_seconds IS NULL OR duration_seconds >= 0", name="ck_stoppage_events_duration_non_negative"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_stoppage_events_confidence_range"),
        UniqueConstraint("tenant_id", "source_event_id", name="uq_stoppage_events_source_event"),
        Index("ix_stoppage_events_tenant_line_started", "tenant_id", "line_id", "started_at"),
        Index("ix_stoppage_events_tenant_station_started", "tenant_id", "station_id", "started_at"),
        Index("ix_stoppage_events_tenant_reason_started", "tenant_id", "reason", "started_at"),
    )


class ProductionIngestClient(Base):
    __tablename__ = "production_ingest_clients"

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), Identity(), primary_key=True)
    client_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String(200), nullable=False)
    api_key_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    plant_code: Mapped[str | None] = mapped_column(String(50))
    line_code: Mapped[str | None] = mapped_column(String(50))
    station_code: Mapped[str | None] = mapped_column(String(50))
    machine_code: Mapped[str | None] = mapped_column(String(50))
    source_system: Mapped[str | None] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("TRUE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=text("CURRENT_TIMESTAMP"), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(50), ForeignKey("tb_tenants.tenant_id"), nullable=False, server_default=text("'DEFAULT'"))

    __table_args__ = (
        CheckConstraint("trim(client_id) <> ''", name="ck_production_ingest_clients_client_id_not_blank"),
        CheckConstraint("trim(description) <> ''", name="ck_production_ingest_clients_description_not_blank"),
        Index("ix_production_ingest_clients_client_id", "client_id"),
        Index("ix_production_ingest_clients_active", "is_active"),
    )


class IntegrationServer(Base):
    """Reusable outbound endpoint with encrypted credentials when authentication needs them."""

    __tablename__ = "integration_servers"

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), Identity(), primary_key=True)
    server_id: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(String(200), nullable=False)
    protocol: Mapped[str] = mapped_column(String(30), nullable=False)
    base_url: Mapped[str | None] = mapped_column(String(500))
    api_endpoint: Mapped[str | None] = mapped_column(String(500))
    work_order_endpoint: Mapped[str | None] = mapped_column(String(500))
    auth_type: Mapped[str] = mapped_column(String(30), server_default=text("'none'"), nullable=False)
    secret_ref: Mapped[str | None] = mapped_column(String(200))
    credentials_encrypted: Mapped[str | None] = mapped_column(Text)
    token_url: Mapped[str | None] = mapped_column(String(500))
    oauth_scope: Mapped[str | None] = mapped_column(String(500))
    token_refresh_buffer_seconds: Mapped[int] = mapped_column(Integer, server_default=text("60"), nullable=False)
    timeout_seconds: Mapped[int] = mapped_column(Integer, server_default=text("30"), nullable=False)
    verify_tls: Mapped[bool] = mapped_column(Boolean, server_default=text("TRUE"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("TRUE"), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(50), ForeignKey("tb_tenants.tenant_id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=text("CURRENT_TIMESTAMP"), nullable=False)

    __table_args__ = (
        CheckConstraint("trim(server_id) <> ''", name="ck_integration_server_id_not_blank"),
        CheckConstraint("trim(description) <> ''", name="ck_integration_server_description_not_blank"),
        CheckConstraint("token_refresh_buffer_seconds >= 0", name="ck_integration_server_token_buffer_non_negative"),
        CheckConstraint("timeout_seconds > 0", name="ck_integration_server_timeout_positive"),
        UniqueConstraint("tenant_id", "server_id", name="uq_integration_server_tenant_server"),
        Index("ix_integration_server_tenant", "tenant_id"),
    )


class IntegrationDeliveryRule(Base):
    """How RupMes production reports are selected and delivered to one ERP endpoint."""

    __tablename__ = "integration_delivery_rules"

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), Identity(), primary_key=True)
    rule_id: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(String(200), nullable=False)
    report_filter: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    mapping_config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    lot_mask: Mapped[str | None] = mapped_column(String(250))
    external_type: Mapped[str | None] = mapped_column(String(100))
    mes_lookup_enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("FALSE"), nullable=False)
    mes_server: Mapped[str | None] = mapped_column(String(250))
    mes_database: Mapped[str | None] = mapped_column(String(250))
    mes_credentials_encrypted: Mapped[str | None] = mapped_column(Text)
    mes_production_status: Mapped[str] = mapped_column(String(100), server_default=text("'IN PROGRESS'"), nullable=False)
    server_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("integration_servers.id"), nullable=False)
    dispatch_interval_seconds: Mapped[int] = mapped_column(Integer, server_default=text("30"), nullable=False)
    batch_size: Mapped[int] = mapped_column(Integer, server_default=text("100"), nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, server_default=text("5"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("TRUE"), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(50), ForeignKey("tb_tenants.tenant_id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=text("CURRENT_TIMESTAMP"), nullable=False)

    __table_args__ = (
        CheckConstraint("trim(rule_id) <> ''", name="ck_integration_delivery_rule_id_not_blank"),
        CheckConstraint("dispatch_interval_seconds > 0", name="ck_integration_delivery_rule_interval_positive"),
        CheckConstraint("batch_size > 0", name="ck_integration_delivery_rule_batch_positive"),
        CheckConstraint("max_retries >= 0", name="ck_integration_delivery_rule_retries_non_negative"),
        UniqueConstraint("tenant_id", "rule_id", name="uq_integration_delivery_rule_tenant_rule"),
        Index("ix_integration_delivery_rule_tenant", "tenant_id"),
        Index("ix_integration_delivery_rule_server", "server_id"),
    )


class IntegrationDeliveryBatch(Base):
    """Durable outbound batch; a report is never selected twice for the same rule."""

    __tablename__ = "integration_delivery_batches"

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), Identity(), primary_key=True)
    rule_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("integration_delivery_rules.id"), nullable=False)
    destination: Mapped[str] = mapped_column(String(30), nullable=False)
    lot_id: Mapped[str | None] = mapped_column(String(250))
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(20), server_default=text("'PENDING'"), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, server_default=text("0"), nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_error: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime)
    tenant_id: Mapped[str] = mapped_column(String(50), ForeignKey("tb_tenants.tenant_id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=text("CURRENT_TIMESTAMP"), nullable=False)

    __table_args__ = (
        CheckConstraint("status IN ('PENDING', 'SENDING', 'SENT', 'FAILED')", name="ck_integration_delivery_batch_status"),
        Index("ix_integration_delivery_batch_ready", "status", "next_attempt_at"),
    )


class IntegrationDeliveryBatchReport(Base):
    __tablename__ = "integration_delivery_batch_reports"

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), Identity(), primary_key=True)
    batch_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("integration_delivery_batches.id", ondelete="CASCADE"), nullable=False)
    rule_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("integration_delivery_rules.id"), nullable=False)
    report_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("production_report.id"), nullable=False)

    __table_args__ = (
        UniqueConstraint("rule_id", "report_id", name="uq_integration_delivery_rule_report"),
        Index("ix_integration_delivery_batch_report_batch", "batch_id"),
    )
