from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator


class StatusCreate(BaseModel):
    status_id: str = Field(..., max_length=50)
    description_status: str = Field(..., max_length=50)


class StatusRead(BaseModel):
    status_id: str
    description_status: str


class StatusUpdate(BaseModel):
    description_status: Optional[str] = Field(None, max_length=50)


class ItemCreate(BaseModel):
    item_id: str = Field(..., max_length=50)
    model_id: str = Field(..., max_length=50)
    line_id: str = Field(..., max_length=50)
    location_id: int
    cell_id: str = Field(..., max_length=50)
    id_user: str = Field(..., max_length=50)
    status_id: str = Field(..., max_length=50)
    value1_int: Optional[int] = None
    value2_int: Optional[int] = None
    value3_int: Optional[int] = None
    value4_int: Optional[int] = None
    value5_int: Optional[int] = None
    value1_str: Optional[str] = Field(None, max_length=50)
    value2_str: Optional[str] = Field(None, max_length=50)
    value3_str: Optional[str] = Field(None, max_length=50)
    value4_str: Optional[str] = Field(None, max_length=50)
    value5_str: Optional[str] = Field(None, max_length=50)


class ItemRead(BaseModel):
    item_id: str
    model_id: str
    line_id: str
    location_id: int
    cell_id: str
    id_user: str
    status_id: str
    create_date: datetime
    last_test_date: datetime
    value1_int: Optional[int]
    value2_int: Optional[int]
    value3_int: Optional[int]
    value4_int: Optional[int]
    value5_int: Optional[int]
    value1_str: Optional[str]
    value2_str: Optional[str]
    value3_str: Optional[str]
    value4_str: Optional[str]
    value5_str: Optional[str]


class UserCreate(BaseModel):
    id_user: str = Field(..., max_length=50)
    name_user: str = Field(..., max_length=50)
    mail_user: EmailStr
    id_group: str = Field(..., max_length=10)
    status_user: str = Field(..., max_length=3)
    password: str = Field(..., min_length=6)
    accessible_tenant_ids: list[str] = []


class UserRead(BaseModel):
    id_user: str
    name_user: str
    mail_user: EmailStr
    id_group: str
    status_user: str
    role_ids: list[str] = []
    accessible_tenant_ids: list[str] = []
    create_date: datetime


class RoutingCreate(BaseModel):
    routing_id: str = Field(..., max_length=50)
    description_routing: str = Field(..., max_length=50)
    line_id: str = Field(..., min_length=1, max_length=50)


class RoutingRead(BaseModel):
    routing_id: str
    description_routing: str
    line_id: str | None = None
    create_date: datetime


class ItemUpdate(BaseModel):
    model_id: Optional[str] = Field(None, max_length=50)
    line_id: Optional[str] = Field(None, max_length=50)
    location_id: Optional[int] = None
    cell_id: Optional[str] = Field(None, max_length=50)
    id_user: Optional[str] = Field(None, max_length=50)
    status_id: Optional[str] = Field(None, max_length=50)
    value1_int: Optional[int] = None
    value2_int: Optional[int] = None
    value3_int: Optional[int] = None
    value4_int: Optional[int] = None
    value5_int: Optional[int] = None
    value1_str: Optional[str] = Field(None, max_length=50)
    value2_str: Optional[str] = Field(None, max_length=50)
    value3_str: Optional[str] = Field(None, max_length=50)
    value4_str: Optional[str] = Field(None, max_length=50)
    value5_str: Optional[str] = Field(None, max_length=50)


class UserUpdate(BaseModel):
    name_user: Optional[str] = Field(None, max_length=50)
    mail_user: Optional[EmailStr] = None
    id_group: Optional[str] = Field(None, max_length=10)
    status_user: Optional[str] = Field(None, max_length=3)
    password: Optional[str] = Field(None, min_length=6)
    accessible_tenant_ids: Optional[list[str]] = None


class UserSelfUpdate(BaseModel):
    name_user: Optional[str] = Field(None, max_length=50)
    mail_user: Optional[EmailStr] = None
    password: Optional[str] = Field(None, min_length=6)


class RoutingUpdate(BaseModel):
    description_routing: Optional[str] = Field(None, max_length=50)
    line_id: Optional[str] = Field(None, min_length=1, max_length=50)


ResultValueType = Literal["text", "number", "integer", "boolean", "select", "date", "datetime"]
RoutingExecutionResult = Literal["OK", "NOK", "SKIPPED"]


class RoutingResultField(BaseModel):
    code: str = Field(..., min_length=1, max_length=50, pattern=r"^[A-Za-z][A-Za-z0-9_]*$")
    label: str = Field(..., min_length=1, max_length=100)
    type: ResultValueType
    required: bool = False
    reportable: bool = False
    unit: str | None = Field(None, max_length=30)
    allowed_values: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("allowed_values")
    @classmethod
    def validate_allowed_values(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("Allowed values must be unique")
        return value


class RoutingProcessCreate(BaseModel):
    process_id: str = Field(..., min_length=1, max_length=50)
    description: str = Field(..., min_length=1, max_length=150)
    cell_id: str = Field(..., min_length=1, max_length=50)
    sequence: int = Field(..., ge=1)
    is_required: bool = True
    result_schema: list[RoutingResultField] = Field(default_factory=list, max_length=50)

    @field_validator("result_schema")
    @classmethod
    def validate_result_schema(cls, value: list[RoutingResultField]) -> list[RoutingResultField]:
        codes = [field.code for field in value]
        if len(codes) != len(set(codes)):
            raise ValueError("Result field codes must be unique per process")
        for field in value:
            if field.type == "select" and not field.allowed_values:
                raise ValueError(f"Select field '{field.code}' requires allowed_values")
            if field.type != "select" and field.allowed_values:
                raise ValueError(f"Only select fields can declare allowed_values")
        return value


class RoutingProcessUpdate(BaseModel):
    description: str | None = Field(None, min_length=1, max_length=150)
    cell_id: str | None = Field(None, min_length=1, max_length=50)
    sequence: int | None = Field(None, ge=1)
    is_required: bool | None = None
    result_schema: list[RoutingResultField] | None = Field(None, max_length=50)


class RoutingProcessRead(RoutingProcessCreate):
    routing_id: str
    create_date: datetime


class RoutingModelCreate(BaseModel):
    model_id: str = Field(..., min_length=1, max_length=50)
    routing_id: str = Field(..., min_length=1, max_length=50)
    is_active: bool = True


class RoutingModelUpdate(BaseModel):
    routing_id: str | None = Field(None, min_length=1, max_length=50)
    is_active: bool | None = None


class RoutingModelRead(RoutingModelCreate):
    create_date: datetime


class RoutingDefinitionRead(RoutingRead):
    processes: list[RoutingProcessRead] = []
    models: list[RoutingModelRead] = []


class RoutingProcessResultCreate(BaseModel):
    model_id: str = Field(..., min_length=1, max_length=50)
    serial_number: str = Field(..., min_length=1, max_length=150)
    process_id: str = Field(..., min_length=1, max_length=50)
    result: RoutingExecutionResult
    result_values: dict[str, Any] = Field(default_factory=dict)
    process_datetime: datetime
    source_system: str | None = Field(None, max_length=100)
    plant_code: str | None = Field(None, max_length=50)
    line_code: str | None = Field(None, max_length=50)
    station_code: str | None = Field(None, max_length=50)
    machine_code: str | None = Field(None, max_length=50)


class RoutingProcessResultRead(RoutingProcessResultCreate):
    id: int
    routing_id: str
    cell_id: str
    result_schema: list[RoutingResultField] = []
    created_at: datetime


class LineCreate(BaseModel):
    line_id: str = Field(..., max_length=50)
    description_line: str = Field(..., max_length=50)
    plant_id: Optional[str] = Field(None, max_length=50)


class LineRead(BaseModel):
    line_id: str
    description_line: str
    plant_id: Optional[str] = None
    create_date: datetime


class LineUpdate(BaseModel):
    description_line: Optional[str] = Field(None, max_length=50)
    plant_id: Optional[str] = Field(None, max_length=50)


class PlantCreate(BaseModel):
    plant_id: str = Field(..., max_length=50)
    description_plant: str = Field(..., max_length=100)


class PlantRead(BaseModel):
    plant_id: str
    description_plant: str
    create_date: datetime


class PlantUpdate(BaseModel):
    description_plant: Optional[str] = Field(None, max_length=100)


class PlantCreate(BaseModel):
    plant_id: str = Field(..., max_length=50)
    description_plant: str = Field(..., max_length=100)


class PlantRead(BaseModel):
    plant_id: str
    description_plant: str
    create_date: datetime


class PlantUpdate(BaseModel):
    description_plant: Optional[str] = Field(None, max_length=100)


class CellCreate(BaseModel):
    cell_id: str = Field(..., max_length=50)
    description_cell: str = Field(..., max_length=50)


class CellRead(BaseModel):
    cell_id: str
    description_cell: str
    create_date: datetime


class CellUpdate(BaseModel):
    description_cell: Optional[str] = Field(None, max_length=50)


class CellLineAssignmentUpdate(BaseModel):
    line_ids: list[str] = Field(default_factory=list)


class ModelCreate(BaseModel):
    model_id: str = Field(..., max_length=50)
    description_model: str = Field(..., max_length=50)


class ModelRead(BaseModel):
    model_id: str
    description_model: str
    create_date: datetime


class ModelUpdate(BaseModel):
    description_model: Optional[str] = Field(None, max_length=50)


class LoginRequest(BaseModel):
    id_user: str = Field(..., max_length=50)
    password: str = Field(..., min_length=6)


class LoginResponse(BaseModel):
    id_user: str
    name_user: str
    mail_user: EmailStr
    tenant_id: str
    roles: list[str]
    permissions: list[str]
    accessible_tenant_ids: list[str] = []


class RoleCreate(BaseModel):
    role_id: str = Field(..., max_length=50)
    description_role: str = Field(..., max_length=100)


class RoleRead(BaseModel):
    role_id: str
    description_role: str
    tenant_id: str


class RoleUpdate(BaseModel):
    description_role: Optional[str] = Field(None, max_length=100)


class PermissionRead(BaseModel):
    permission_id: str
    description_permission: str


class RolePermissionsUpdate(BaseModel):
    permission_ids: list[str]


class UserRolesUpdate(BaseModel):
    role_ids: list[str]


class GroupRead(BaseModel):
    id_group: str
    name_group: str
    level_group: int


class GroupCreate(BaseModel):
    id_group: str = Field(..., max_length=10)
    name_group: str = Field(..., max_length=50)
    level_group: int


class TenantRead(BaseModel):
    tenant_id: str
    name_tenant: str
    is_active: bool
    is_default: bool
    create_date: datetime


class TenantCreate(BaseModel):
    tenant_id: str = Field(..., max_length=50)
    name_tenant: str = Field(..., max_length=100)
    is_active: bool = True
    is_default: bool = False

    @field_validator("tenant_id", "name_tenant")
    @classmethod
    def validate_tenant_fields(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Value cannot be empty")
        return cleaned


class TenantUpdate(BaseModel):
    name_tenant: Optional[str] = Field(None, max_length=100)
    is_active: Optional[bool] = None
    is_default: Optional[bool] = None

    @field_validator("name_tenant")
    @classmethod
    def validate_tenant_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Value cannot be empty")
        return cleaned


class PortalSettingsRead(BaseModel):
    tenant_id: str
    portal_title: str
    logo_image: Optional[str] = None


class PortalSettingsUpdate(BaseModel):
    portal_title: str = Field(..., max_length=100)
    logo_image: Optional[str] = None

    @field_validator("portal_title")
    @classmethod
    def validate_portal_title(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Value cannot be empty")
        return cleaned


class LoginContextRead(BaseModel):
    multi_tenant_enabled: bool
    default_tenant_id: str
    tenants: list[TenantRead]


class UserStatusCatalogRead(BaseModel):
    status_user: str
    description_status: str


AllowedProductionResult = Literal["OK", "NOK", "SCRAP", "REWORK"]
ProductionReportType = Literal["WIP", "FINISHED_PART", "FINISHED_BOX"]


class ProductionReportCreate(BaseModel):
    plant_code: Optional[str] = Field(None, max_length=50)
    line_code: str = Field(..., max_length=50)
    station_code: Optional[str] = Field(None, max_length=50)
    machine_code: Optional[str] = Field(None, max_length=50)
    shift_code: Optional[str] = Field(None, max_length=20)
    production_order: Optional[str] = Field(None, max_length=100)
    product_code: Optional[str] = Field(None, max_length=100)
    product_family: Optional[str] = Field(None, max_length=100)
    customer: Optional[str] = Field(None, max_length=100)
    report_type: ProductionReportType = "FINISHED_PART"
    quantity: Decimal = Field(Decimal("1"), gt=0, decimal_places=3)
    unit_of_measure: str = Field("EA", min_length=1, max_length=20)
    serial_number: Optional[str] = Field(None, max_length=150)
    container_serial: Optional[str] = Field(None, max_length=150)
    material_lot: Optional[str] = Field(None, max_length=100)
    source_event_id: Optional[str] = Field(None, max_length=150)
    result: AllowedProductionResult
    error_code: Optional[str] = Field(None, max_length=50)
    error_description: Optional[str] = None
    defect_station: Optional[str] = Field(None, max_length=50)
    production_datetime: datetime
    cycle_time_seconds: Optional[Decimal] = Field(None, decimal_places=3)
    target_cycle_time_seconds: Optional[Decimal] = Field(None, decimal_places=3)
    component_serial: Optional[str] = Field(None, max_length=150)
    component_lot: Optional[str] = Field(None, max_length=100)
    supplier_code: Optional[str] = Field(None, max_length=100)
    nest_number: Optional[int] = None
    tool_id: Optional[str] = Field(None, max_length=100)
    program_name: Optional[str] = Field(None, max_length=100)
    software_version: Optional[str] = Field(None, max_length=100)
    is_rework: bool = False
    rework_result: Optional[AllowedProductionResult] = None
    rework_datetime: Optional[datetime] = None
    source_system: Optional[str] = Field(None, max_length=100)

    @field_validator("line_code")
    @classmethod
    def validate_not_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Value cannot be empty")
        return cleaned

    @model_validator(mode="after")
    def validate_report_type(self) -> "ProductionReportCreate":
        self.unit_of_measure = self.unit_of_measure.strip()
        if not self.unit_of_measure:
            raise ValueError("unit_of_measure cannot be empty")
        if self.serial_number is not None:
            self.serial_number = self.serial_number.strip() or None
        if self.report_type in ("FINISHED_PART", "FINISHED_BOX") and not self.serial_number:
            raise ValueError("serial_number is required for finished parts and boxes")
        if self.report_type == "WIP" and not (self.product_code or self.material_lot or self.source_event_id):
            raise ValueError("WIP reports need product_code, material_lot, or source_event_id")
        return self


class ProductionReportIngestCreate(ProductionReportCreate):
    """Machine-to-machine payload.

    Industrial context is optionally supplied by the client but, when the
    authenticated ingest client has it configured, the API is authoritative
    and fills it in server-side.
    """

    line_code: Optional[str] = Field(None, max_length=50)

    @field_validator("line_code")
    @classmethod
    def validate_optional_line_code(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Value cannot be empty")
        return cleaned


StoppageReason = Literal["FAULT", "MANUAL", "STOPPED", "WAITING", "COMMUNICATION_LOSS"]


class StoppageEventIngest(BaseModel):
    source_event_id: str = Field(..., min_length=1, max_length=64)
    line_id: str = Field(..., min_length=1, max_length=100)
    station_id: str = Field(..., min_length=1, max_length=100)
    started_at: datetime
    ended_at: datetime | None = None
    duration_seconds: Decimal | None = Field(None, ge=0, decimal_places=3)
    reason: StoppageReason
    source_state: str = Field(..., min_length=1, max_length=40)
    shift: Literal["TM", "TT", "TN"]
    confidence: Decimal = Field(..., ge=0, le=1, decimal_places=3)
    edge_updated_at: datetime

    @model_validator(mode="after")
    def validate_time_range(self) -> "StoppageEventIngest":
        if self.ended_at is not None and self.ended_at < self.started_at:
            raise ValueError("ended_at cannot precede started_at")
        return self


class StoppageBatchIngest(BaseModel):
    events: list[StoppageEventIngest] = Field(..., min_length=1, max_length=200)


class StoppageBatchIngestResult(BaseModel):
    accepted: int
    inserted: int
    updated: int


class ProductionReportRead(BaseModel):
    id: int
    plant_code: Optional[str]
    line_code: str
    station_code: Optional[str]
    machine_code: Optional[str]
    shift_code: Optional[str]
    production_order: Optional[str]
    product_code: Optional[str]
    product_family: Optional[str]
    customer: Optional[str]
    report_type: ProductionReportType
    quantity: Decimal
    unit_of_measure: str
    serial_number: Optional[str]
    container_serial: Optional[str]
    material_lot: Optional[str]
    source_event_id: Optional[str]
    result: AllowedProductionResult
    error_code: Optional[str]
    error_description: Optional[str]
    defect_station: Optional[str]
    production_datetime: datetime
    cycle_time_seconds: Optional[Decimal]
    target_cycle_time_seconds: Optional[Decimal]
    component_serial: Optional[str]
    component_lot: Optional[str]
    supplier_code: Optional[str]
    nest_number: Optional[int]
    tool_id: Optional[str]
    program_name: Optional[str]
    software_version: Optional[str]
    is_rework: bool
    rework_result: Optional[AllowedProductionResult]
    rework_datetime: Optional[datetime]
    source_system: Optional[str]
    created_at: datetime


class DailyProductionTotalRead(BaseModel):
    production_day: date
    total_production: int


class ProductionByLineRead(BaseModel):
    line_code: str
    total_production: int


class OkNokByShiftRead(BaseModel):
    shift_code: Optional[str]
    ok_count: int
    nok_count: int
    scrap_count: int
    rework_count: int


class FtqFpyRead(BaseModel):
    production_day: date
    line_code: str
    first_pass_total: int
    first_pass_ok: int
    ftq_percent: float
    serial_total: int
    serial_ok: int
    fpy_percent: float


class TopDefectRead(BaseModel):
    error_code: str
    error_description: Optional[str]
    defect_count: int


class PackagingPartsCountRead(BaseModel):
    station_code: str
    parts_count: int


class AverageCycleTimeByLineRead(BaseModel):
    line_code: str
    average_cycle_time_seconds: float
    sample_count: int


class ProductionIngestClientCreate(BaseModel):
    client_id: str = Field(..., max_length=100)
    description: str = Field(..., max_length=200)
    api_key: str = Field(..., min_length=12, max_length=255)
    plant_code: Optional[str] = Field(None, max_length=50)
    line_code: Optional[str] = Field(None, max_length=50)
    station_code: Optional[str] = Field(None, max_length=50)
    machine_code: Optional[str] = Field(None, max_length=50)
    source_system: Optional[str] = Field(None, max_length=100)
    is_active: bool = True

    @field_validator("client_id", "description")
    @classmethod
    def validate_client_not_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Value cannot be empty")
        return cleaned


class ProductionIngestClientRead(BaseModel):
    client_id: str
    description: str
    plant_code: Optional[str]
    line_code: Optional[str]
    station_code: Optional[str]
    machine_code: Optional[str]
    source_system: Optional[str]
    is_active: bool
    created_at: datetime


class ProductionIngestClientUpdate(BaseModel):
    description: Optional[str] = Field(None, max_length=200)
    api_key: Optional[str] = Field(None, min_length=12, max_length=255)
    plant_code: Optional[str] = Field(None, max_length=50)
    line_code: Optional[str] = Field(None, max_length=50)
    station_code: Optional[str] = Field(None, max_length=50)
    machine_code: Optional[str] = Field(None, max_length=50)
    source_system: Optional[str] = Field(None, max_length=100)
    is_active: Optional[bool] = None

    @field_validator("description")
    @classmethod
    def validate_optional_description(cls, value: str | None) -> str | None:
        if value is None:
            return value
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Value cannot be empty")
        return cleaned


class IntegrationServerCreate(BaseModel):
    server_id: str = Field(..., max_length=100)
    description: str = Field(..., max_length=200)
    protocol: str = Field(..., max_length=30)
    base_url: Optional[str] = Field(None, max_length=500)
    api_endpoint: Optional[str] = Field(None, max_length=500)
    work_order_endpoint: Optional[str] = Field(None, max_length=500)
    auth_type: str = Field("none", max_length=30)
    secret_ref: Optional[str] = Field(None, max_length=200)
    oauth_client_id: Optional[str] = Field(None, max_length=500)
    oauth_client_secret: Optional[str] = Field(None, max_length=2000)
    token_url: Optional[str] = Field(None, max_length=500)
    oauth_scope: Optional[str] = Field(None, max_length=500)
    token_refresh_buffer_seconds: int = Field(60, ge=0, le=3600)
    timeout_seconds: int = Field(30, ge=1, le=300)
    verify_tls: bool = True
    is_active: bool = True

    @field_validator("server_id", "description", "protocol")
    @classmethod
    def validate_server_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Value cannot be empty")
        return value


class IntegrationServerRead(BaseModel):
    id: int
    server_id: str
    description: str
    protocol: str
    base_url: Optional[str]
    api_endpoint: Optional[str]
    work_order_endpoint: Optional[str]
    auth_type: str
    secret_ref: Optional[str]
    credentials_configured: bool
    token_url: Optional[str]
    oauth_scope: Optional[str]
    token_refresh_buffer_seconds: int
    timeout_seconds: int
    verify_tls: bool
    is_active: bool
    created_at: datetime


class IntegrationServerUpdate(BaseModel):
    description: Optional[str] = Field(None, max_length=200)
    protocol: Optional[str] = Field(None, max_length=30)
    base_url: Optional[str] = Field(None, max_length=500)
    api_endpoint: Optional[str] = Field(None, max_length=500)
    work_order_endpoint: Optional[str] = Field(None, max_length=500)
    auth_type: Optional[str] = Field(None, max_length=30)
    secret_ref: Optional[str] = Field(None, max_length=200)
    oauth_client_id: Optional[str] = Field(None, max_length=500)
    oauth_client_secret: Optional[str] = Field(None, max_length=2000)
    token_url: Optional[str] = Field(None, max_length=500)
    oauth_scope: Optional[str] = Field(None, max_length=500)
    token_refresh_buffer_seconds: Optional[int] = Field(None, ge=0, le=3600)
    timeout_seconds: Optional[int] = Field(None, ge=1, le=300)
    verify_tls: Optional[bool] = None
    is_active: Optional[bool] = None


class IntegrationDeliveryRuleCreate(BaseModel):
    rule_id: str = Field(..., max_length=100)
    description: str = Field(..., max_length=200)
    report_filter: dict = Field(default_factory=dict)
    mapping_config: dict = Field(default_factory=dict)
    lot_mask: Optional[str] = Field(None, max_length=250)
    external_type: Optional[str] = Field(None, max_length=100)
    mes_lookup_enabled: bool = False
    mes_server: Optional[str] = Field(None, max_length=250)
    mes_database: Optional[str] = Field(None, max_length=250)
    mes_username: Optional[str] = Field(None, max_length=250)
    mes_password: Optional[str] = Field(None, max_length=1000)
    mes_production_status: str = Field("IN PROGRESS", max_length=100)
    server_id: int
    dispatch_interval_seconds: int = Field(30, ge=1, le=86400)
    batch_size: int = Field(100, ge=1, le=10000)
    max_retries: int = Field(5, ge=0, le=100)
    is_active: bool = True

    @field_validator("rule_id", "description")
    @classmethod
    def validate_rule_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Value cannot be empty")
        return value


class IntegrationDeliveryRuleRead(IntegrationDeliveryRuleCreate):
    id: int
    server_code: str
    created_at: datetime


class IntegrationDeliveryRuleUpdate(BaseModel):
    description: Optional[str] = Field(None, max_length=200)
    report_filter: Optional[dict] = None
    mapping_config: Optional[dict] = None
    lot_mask: Optional[str] = Field(None, max_length=250)
    external_type: Optional[str] = Field(None, max_length=100)
    mes_lookup_enabled: Optional[bool] = None
    mes_server: Optional[str] = Field(None, max_length=250)
    mes_database: Optional[str] = Field(None, max_length=250)
    mes_username: Optional[str] = Field(None, max_length=250)
    mes_password: Optional[str] = Field(None, max_length=1000)
    mes_production_status: Optional[str] = Field(None, max_length=100)
    server_id: Optional[int] = None
    dispatch_interval_seconds: Optional[int] = Field(None, ge=1, le=86400)
    batch_size: Optional[int] = Field(None, ge=1, le=10000)
    max_retries: Optional[int] = Field(None, ge=0, le=100)
    is_active: Optional[bool] = None
