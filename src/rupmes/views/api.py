from datetime import date, datetime, time

import httpx

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from rupmes.controllers.items_controller import (
    create_item,
    delete_item,
    get_item,
    list_items,
    update_item,
)
from rupmes.controllers.groups_controller import list_groups
from rupmes.controllers.groups_write_controller import create_group
from rupmes.controllers.portal_settings_controller import get_portal_settings, save_portal_settings
from rupmes.controllers.production_report_controller import (
    create_production_report,
    get_average_cycle_time_by_line,
    get_daily_totals,
    get_ftq_fpy_by_line_and_day,
    get_ok_nok_by_shift,
    get_production_by_line,
    get_production_report,
    get_top_defects,
    get_traceability,
)
from rupmes.controllers.production_ingest_clients_controller import (
    create_production_ingest_client,
    delete_production_ingest_client,
    get_production_ingest_client,
    list_production_ingest_clients,
    update_production_ingest_client,
)
from rupmes.controllers.lines_controller import (
    create_line,
    delete_line,
    get_line,
    list_lines,
    update_line,
)
from rupmes.controllers.cells_controller import (
    create_cell,
    delete_cell,
    get_cell,
    list_cells,
    update_cell,
)
from rupmes.controllers.models_controller import (
    create_model,
    delete_model,
    get_model,
    list_models,
    update_model,
)
from rupmes.controllers.routings_controller import (
    create_routing,
    delete_routing,
    get_routing,
    list_routings,
    update_routing,
)
from rupmes.controllers.routing_execution_controller import (
    create_routing_process,
    create_routing_process_result,
    create_routing_model,
    delete_routing_process,
    delete_routing_model,
    get_routing_process,
    get_routing_model,
    list_routing_process_results,
    list_routing_processes,
    list_routing_models,
    update_routing_process,
    update_routing_model,
)
from rupmes.controllers.status_controller import create_status, delete_status, get_status, list_statuses
from rupmes.controllers.tenants_controller import create_tenant, get_default_tenant, get_tenant, list_tenants, update_tenant
from rupmes.controllers.users_controller import (
    create_user,
    delete_user,
    get_user,
    list_users,
    update_user,
)
from rupmes.controllers.user_roles_controller import list_user_roles, replace_user_roles
from rupmes.controllers.user_tenants_controller import list_user_tenants, replace_user_tenants
from rupmes.core.config import get_app_version, get_default_tenant_id, get_frontend_origins, is_multi_tenant_enabled
from rupmes.core.deps import get_db
from rupmes.core.i18n import get_lang, translate_error, translate_validation
from rupmes.core.tenant import resolve_tenant_id
from rupmes.models import (
    ProductionReport,
    RoutingProcess,
    RoutingProcessResult,
    RoutingModel,
    TbCells,
    TbGroups,
    TbItems,
    TbLines,
    TbPlants,
    HrefCellLine,
    TbModels,
    TbPortalSettings,
    TbRoutings,
    TbStatus,
    TbTenants,
    TbUsers,
)
from rupmes.models import IntegrationDeliveryRule, IntegrationServer, ProductionIngestClient, StoppageEvent, TraceabilityMeasurement
from rupmes.services.security import hash_password
from rupmes.services.integration_credentials import decrypt_oauth_credentials, encrypt_oauth_credentials
from rupmes.views.auth import (
    get_current_session,
    get_current_user,
    require_admin,
    require_csrf,
    require_permission,
    require_production_ingest_api_key,
    require_tenant_access,
    router as auth_router,
)
from rupmes.controllers.user_status_controller import list_user_statuses
from rupmes.views.schemas import (
    AverageCycleTimeByLineRead,
    GroupCreate,
    GroupRead,
    ItemCreate,
    ItemRead,
    ItemUpdate,
    DailyProductionTotalRead,
    FtqFpyRead,
    LineCreate,
    LineRead,
    LineUpdate,
    PlantCreate,
    PlantRead,
    PlantUpdate,
    LoginContextRead,
    CellCreate,
    CellRead,
    CellUpdate,
    CellLineAssignmentUpdate,
    ModelCreate,
    ModelRead,
    ModelUpdate,
    RoutingCreate,
    RoutingDefinitionRead,
    RoutingProcessCreate,
    RoutingProcessRead,
    RoutingProcessResultCreate,
    RoutingProcessResultRead,
    RoutingProcessUpdate,
    RoutingModelCreate,
    RoutingModelRead,
    RoutingModelUpdate,
    RoutingRead,
    RoutingUpdate,
    ProductionByLineRead,
    ProductionIngestClientCreate,
    ProductionIngestClientRead,
    ProductionIngestClientUpdate,
    IntegrationDeliveryRuleCreate,
    IntegrationDeliveryRuleRead,
    IntegrationDeliveryRuleUpdate,
    IntegrationServerCreate,
    IntegrationServerRead,
    IntegrationServerUpdate,
    ProductionReportCreate,
    ProductionReportIngestCreate,
    ProductionReportRead,
    StoppageBatchIngest,
    StoppageBatchIngestResult,
    StatusCreate,
    StatusRead,
    StatusUpdate,
    TopDefectRead,
    OkNokByShiftRead,
    PortalSettingsRead,
    PortalSettingsUpdate,
    UserStatusCatalogRead,
    TenantCreate,
    TenantRead,
    TenantUpdate,
    UserCreate,
    UserRead,
    UserSelfUpdate,
    UserUpdate,
)


app = FastAPI(title="RupMes Trazability API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_frontend_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    lang = get_lang(request)
    detail = exc.detail
    if isinstance(detail, str):
        detail = translate_error(detail, lang)
    return JSONResponse(status_code=exc.status_code, content={"detail": detail})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    lang = get_lang(request)
    detail = translate_validation(exc.errors(), lang)
    return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content={"detail": detail})


def _parse_datetime_filter(value: str | None, end_of_day: bool = False):
    if not value:
        return None
    try:
        if len(value) == 10:
            parsed = date.fromisoformat(value)
            return datetime.combine(parsed, time.max if end_of_day else time.min)
        return datetime.fromisoformat(value)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid date format")


def _coerce_date(value):
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _serialize_production_report(row: ProductionReport) -> ProductionReportRead:
    return ProductionReportRead(
        id=row.id,
        plant_code=row.plant_code,
        line_code=row.line_code,
        station_code=row.station_code,
        machine_code=row.machine_code,
        shift_code=row.shift_code,
        production_order=row.production_order,
        product_code=row.product_code,
        product_family=row.product_family,
        customer=row.customer,
        serial_number=row.serial_number,
        result=row.result,
        error_code=row.error_code,
        error_description=row.error_description,
        defect_station=row.defect_station,
        production_datetime=row.production_datetime,
        cycle_time_seconds=row.cycle_time_seconds,
        target_cycle_time_seconds=row.target_cycle_time_seconds,
        component_serial=row.component_serial,
        component_lot=row.component_lot,
        supplier_code=row.supplier_code,
        nest_number=row.nest_number,
        tool_id=row.tool_id,
        program_name=row.program_name,
        software_version=row.software_version,
        is_rework=row.is_rework,
        rework_result=row.rework_result,
        rework_datetime=row.rework_datetime,
        source_system=row.source_system,
        created_at=row.created_at,
    )


def _serialize_production_ingest_client(row: ProductionIngestClient) -> ProductionIngestClientRead:
    return ProductionIngestClientRead(
        client_id=row.client_id,
        description=row.description,
        plant_code=row.plant_code,
        line_code=row.line_code,
        station_code=row.station_code,
        machine_code=row.machine_code,
        source_system=row.source_system,
        is_active=row.is_active,
        created_at=row.created_at,
    )


def _serialize_integration_server(row: IntegrationServer) -> IntegrationServerRead:
    return IntegrationServerRead(
        id=row.id, server_id=row.server_id, description=row.description, protocol=row.protocol,
        base_url=row.base_url, api_endpoint=row.api_endpoint, auth_type=row.auth_type, secret_ref=row.secret_ref,
        credentials_configured=bool(row.credentials_encrypted),
        token_url=row.token_url, oauth_scope=row.oauth_scope,
        token_refresh_buffer_seconds=row.token_refresh_buffer_seconds,
        timeout_seconds=row.timeout_seconds, verify_tls=row.verify_tls, is_active=row.is_active,
        created_at=row.created_at,
    )


def _apply_integration_server_credentials(values: dict) -> dict:
    """Keep OAuth credentials write-only and encrypted before they reach the database."""
    client_id = (values.pop("oauth_client_id", None) or "").strip()
    client_secret = values.pop("oauth_client_secret", None) or ""
    if not client_id and not client_secret:
        return values
    if not client_id or not client_secret:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="OAuth client ID and secret must be provided together")
    try:
        values["credentials_encrypted"] = encrypt_oauth_credentials(client_id, client_secret)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    return values


def _test_oauth_client_credentials(row: IntegrationServer) -> int | None:
    if row.auth_type != "oauth2_client_credentials":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Connection test currently supports OAuth2 client credentials only")
    if not row.token_url:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OAuth token URL is not configured")
    try:
        client_id, client_secret = decrypt_oauth_credentials(row.credentials_encrypted)
        with httpx.Client(verify=row.verify_tls, timeout=row.timeout_seconds) as client:
            response = client.post(row.token_url, data={"grant_type": "client_credentials", **({"scope": row.oauth_scope} if row.oauth_scope else {})}, auth=(client_id, client_secret))
        response.raise_for_status()
        body = response.json()
        if not body.get("access_token"):
            raise ValueError("Token endpoint did not return an access token")
        return body.get("expires_in")
    except HTTPException:
        raise
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"OAuth connection test failed: {exc}") from exc


def _serialize_integration_delivery_rule(row: IntegrationDeliveryRule, server: IntegrationServer) -> IntegrationDeliveryRuleRead:
    return IntegrationDeliveryRuleRead(
        id=row.id, rule_id=row.rule_id, description=row.description,
        report_filter=row.report_filter or {}, mapping_config=row.mapping_config or {}, lot_mask=row.lot_mask,
        server_id=row.server_id, server_code=server.server_id,
        dispatch_interval_seconds=row.dispatch_interval_seconds, batch_size=row.batch_size,
        max_retries=row.max_retries, is_active=row.is_active, created_at=row.created_at,
    )


def _serialize_routing_process(row: RoutingProcess) -> RoutingProcessRead:
    return RoutingProcessRead(
        routing_id=row.routing_id,
        process_id=row.process_id,
        description=row.description,
        cell_id=row.cell_id,
        sequence=row.sequence,
        is_required=row.is_required,
        result_schema=row.result_schema or [],
        create_date=row.create_date,
    )


def _serialize_routing_model(row: RoutingModel) -> RoutingModelRead:
    return RoutingModelRead(
        model_id=row.model_id,
        routing_id=row.routing_id,
        is_active=row.is_active,
        create_date=row.create_date,
    )


def _serialize_routing_process_result(row: RoutingProcessResult) -> RoutingProcessResultRead:
    return RoutingProcessResultRead(
        id=row.id,
        model_id=row.model_id,
        serial_number=row.serial_number,
        routing_id=row.routing_id,
        process_id=row.process_id,
        cell_id=row.cell_id,
        result=row.result,
        result_values=row.result_values or {},
        result_schema=row.result_schema or [],
        process_datetime=row.process_datetime,
        source_system=row.source_system,
        created_at=row.created_at,
    )


def _validate_result_values(process: RoutingProcess, result: str, values: dict) -> None:
    fields = process.result_schema or []
    field_by_code = {field["code"]: field for field in fields}
    unknown = sorted(set(values) - set(field_by_code))
    if unknown:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=f"Unknown result fields: {', '.join(unknown)}")
    if result == "SKIPPED":
        return
    for code, field in field_by_code.items():
        if field.get("required") and (code not in values or values[code] is None or values[code] == ""):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=f"Required result field missing: {code}")
        if code not in values or values[code] is None:
            continue
        value = values[code]
        field_type = field["type"]
        if field_type == "text" and not isinstance(value, str):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=f"Result field '{code}' must be text")
        if field_type == "number" and (not isinstance(value, (int, float)) or isinstance(value, bool)):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=f"Result field '{code}' must be numeric")
        if field_type == "integer" and (not isinstance(value, int) or isinstance(value, bool)):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=f"Result field '{code}' must be an integer")
        if field_type == "boolean" and not isinstance(value, bool):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=f"Result field '{code}' must be boolean")
        if field_type == "select" and value not in field.get("allowed_values", []):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=f"Invalid option for result field '{code}'")
        if field_type == "date":
            try:
                date.fromisoformat(value)
            except (TypeError, ValueError):
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=f"Result field '{code}' must be an ISO date")
        if field_type == "datetime":
            try:
                datetime.fromisoformat(value)
            except (TypeError, ValueError):
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=f"Result field '{code}' must be an ISO datetime")


def _build_traceability_measurements(process: RoutingProcess, payload: RoutingProcessResultCreate, routing_id: str, cell_id: str, tenant_id: str) -> list[TraceabilityMeasurement]:
    measurements: list[TraceabilityMeasurement] = []
    for field in process.result_schema or []:
        code = field["code"]
        value = payload.result_values.get(code)
        if not field.get("reportable") or value is None:
            continue
        measurement = TraceabilityMeasurement(
            event_id=0,
            tenant_id=tenant_id,
            serial_number=payload.serial_number,
            model_id=payload.model_id,
            routing_id=routing_id,
            process_id=payload.process_id,
            cell_id=cell_id,
            result=payload.result,
            measurement_code=code,
            measurement_type=field["type"],
            unit=field.get("unit"),
            process_datetime=payload.process_datetime,
        )
        if field["type"] in ("number", "integer"):
            measurement.numeric_value = float(value)
        elif field["type"] == "boolean":
            measurement.boolean_value = value
        elif field["type"] == "datetime":
            measurement.datetime_value = datetime.fromisoformat(value)
        elif field["type"] == "date":
            measurement.datetime_value = datetime.combine(date.fromisoformat(value), time.min)
        else:
            measurement.text_value = str(value)
        measurements.append(measurement)
    return measurements


def _serialize_tenant(row: TbTenants) -> TenantRead:
    return TenantRead(
        tenant_id=row.tenant_id,
        name_tenant=row.name_tenant,
        is_active=row.is_active,
        is_default=row.is_default,
        create_date=row.create_date,
    )


def _serialize_portal_settings(row: TbPortalSettings | None, tenant_id: str) -> PortalSettingsRead:
    if not row:
        return PortalSettingsRead(tenant_id=tenant_id, portal_title="RupMes", logo_image=None)
    return PortalSettingsRead(
        tenant_id=row.tenant_id,
        portal_title=row.portal_title,
        logo_image=row.logo_image,
    )


def _serialize_user(db: Session, row: TbUsers) -> UserRead:
    return UserRead(
        id_user=row.id_user,
        name_user=row.name_user,
        mail_user=row.mail_user,
        id_group=row.id_group,
        status_user=row.status_user,
        role_ids=[role.role_id for role in list_user_roles(db, row.id_user)],
        accessible_tenant_ids=sorted({tenant.tenant_id for tenant in list_user_tenants(db, row.id_user)} | {row.tenant_id}),
        create_date=row.create_date,
    )


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/version")
def version():
    return {"version": get_app_version()}


@app.get("/portal-settings", response_model=PortalSettingsRead)
def get_portal_settings_endpoint(request: Request, db: Session = Depends(get_db)):
    tenant_id = resolve_tenant_id(request)
    row = get_portal_settings(db, tenant_id)
    return _serialize_portal_settings(row, tenant_id)


@app.get("/public/login-context", response_model=LoginContextRead)
def get_login_context_endpoint(db: Session = Depends(get_db)):
    active_tenants = list_tenants(db, active_only=True)
    default_tenant = get_default_tenant(db, active_only=True)
    fallback_tenant_id = default_tenant.tenant_id if default_tenant else get_default_tenant_id()
    return LoginContextRead(
        multi_tenant_enabled=is_multi_tenant_enabled(),
        default_tenant_id=fallback_tenant_id,
        tenants=[_serialize_tenant(row) for row in active_tenants],
    )


@app.put("/portal-settings", response_model=PortalSettingsRead)
def update_portal_settings_endpoint(
    payload: PortalSettingsUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current=Depends(require_admin),
):
    _user, session_row = current
    require_csrf(request, session_row)
    tenant_id = resolve_tenant_id(request)
    row = get_portal_settings(db, tenant_id)
    if not row:
        row = TbPortalSettings(tenant_id=tenant_id, portal_title=payload.portal_title, logo_image=payload.logo_image)
    else:
        row.portal_title = payload.portal_title
        row.logo_image = payload.logo_image
    row = save_portal_settings(db, row)
    return _serialize_portal_settings(row, tenant_id)


@app.get("/tenants", response_model=list[TenantRead])
def list_tenants_endpoint(
    db: Session = Depends(get_db),
    current=Depends(get_current_user),
):
    user = current
    all_tenants = list_tenants(db)
    user_tenant_ids = {tenant.tenant_id for tenant in list_user_tenants(db, user.id_user)}
    user_tenant_ids.add(user.tenant_id)
    is_admin = any(role.role_id == "ADM" for role in list_user_roles(db, user.id_user))
    visible = all_tenants if is_admin else [row for row in all_tenants if row.tenant_id in user_tenant_ids and row.is_active]
    return [_serialize_tenant(row) for row in visible]


@app.get("/tenants/{tenant_id}", response_model=TenantRead)
def get_tenant_endpoint(
    tenant_id: str,
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    row = get_tenant(db, tenant_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return _serialize_tenant(row)


@app.post("/tenants", response_model=TenantRead, status_code=status.HTTP_201_CREATED)
def create_tenant_endpoint(
    payload: TenantCreate,
    request: Request,
    db: Session = Depends(get_db),
    current=Depends(require_admin),
):
    _user, session_row = current
    require_csrf(request, session_row)
    tenant = TbTenants(
        tenant_id=payload.tenant_id,
        name_tenant=payload.name_tenant,
        is_active=payload.is_active,
        is_default=payload.is_default,
    )
    try:
        row = create_tenant(db, tenant)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Tenant already exists")
    save_portal_settings(db, TbPortalSettings(tenant_id=row.tenant_id, portal_title=row.name_tenant, logo_image=None))
    return _serialize_tenant(row)


@app.patch("/tenants/{tenant_id}", response_model=TenantRead)
def update_tenant_endpoint(
    tenant_id: str,
    payload: TenantUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current=Depends(require_admin),
):
    _user, session_row = current
    require_csrf(request, session_row)
    row = get_tenant(db, tenant_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(row, field, value)
    try:
        row = update_tenant(db, row)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Update conflict")
    return _serialize_tenant(row)


@app.get("/groups", response_model=list[GroupRead])
def groups_endpoint(
    db: Session = Depends(get_db),
    _perm=Depends(require_permission("users.read")),
    _admin=Depends(require_admin),
):
    rows = list_groups(db)
    return [GroupRead(id_group=row.id_group, name_group=row.name_group, level_group=row.level_group) for row in rows]


@app.post("/groups", response_model=GroupRead, status_code=status.HTTP_201_CREATED)
def create_group_endpoint(
    payload: GroupCreate,
    request: Request,
    db: Session = Depends(get_db),
    current=Depends(require_permission("users.write")),
    _admin=Depends(require_admin),
):
    _user, session_row = current
    require_csrf(request, session_row)
    group = TbGroups(id_group=payload.id_group, name_group=payload.name_group, level_group=payload.level_group)
    try:
        row = create_group(db, group)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Group already exists")
    return GroupRead(id_group=row.id_group, name_group=row.name_group, level_group=row.level_group)


@app.get("/user-statuses", response_model=list[UserStatusCatalogRead])
def user_statuses_endpoint(
    db: Session = Depends(get_db),
    _perm=Depends(require_permission("users.read")),
    _admin=Depends(require_admin),
):
    rows = list_user_statuses(db)
    return [UserStatusCatalogRead(status_user=row.status_user, description_status=row.description_status) for row in rows]


@app.get("/production-ingest-clients", response_model=list[ProductionIngestClientRead])
def list_production_ingest_clients_endpoint(
    request: Request,
    db: Session = Depends(get_db),
    current=Depends(require_permission("production.admin")),
):
    user, _session_row = current
    tenant_id = require_tenant_access(request, user, db)
    rows = list_production_ingest_clients(db, tenant_id=tenant_id)
    return [_serialize_production_ingest_client(row) for row in rows]


@app.get("/production-ingest-clients/master-data")
def production_ingest_client_master_data(request: Request, db: Session = Depends(get_db), current=Depends(require_permission("production.admin"))):
    user, _session = current
    tenant_id = require_tenant_access(request, user, db)
    plants = db.execute(select(TbPlants).where(TbPlants.tenant_id == tenant_id).order_by(TbPlants.plant_id)).scalars().all()
    lines = db.execute(select(TbLines).where(TbLines.tenant_id == tenant_id).order_by(TbLines.line_id)).scalars().all()
    cells = db.execute(select(TbCells).where(TbCells.tenant_id == tenant_id).order_by(TbCells.cell_id)).scalars().all()
    links = db.execute(select(HrefCellLine).join(TbCells, HrefCellLine.cell_id == TbCells.cell_id).where(TbCells.tenant_id == tenant_id)).scalars().all()
    return {"plants": [{"id": x.plant_id, "description": x.description_plant} for x in plants], "lines": [{"id": x.line_id, "description": x.description_line} for x in lines], "cells": [{"id": x.cell_id, "description": x.description_cell} for x in cells], "cell_lines": [{"cell_id": x.cell_id, "line_id": x.line_id} for x in links]}


def _validate_ingest_client_context(db: Session, tenant_id: str, plant: str | None, line: str | None, cell: str | None):
    if plant and not db.execute(select(TbPlants.id_row).where(TbPlants.tenant_id == tenant_id, TbPlants.plant_id == plant)).scalar_one_or_none():
        raise HTTPException(status_code=422, detail="Plant master not found")
    if line and not db.execute(select(TbLines.id_row).where(TbLines.tenant_id == tenant_id, TbLines.line_id == line)).scalar_one_or_none():
        raise HTTPException(status_code=422, detail="Line master not found")
    if cell and not db.execute(select(TbCells.id_row).where(TbCells.tenant_id == tenant_id, TbCells.cell_id == cell)).scalar_one_or_none():
        raise HTTPException(status_code=422, detail="Cell master not found")
    if line and cell and not db.execute(select(HrefCellLine.id_row).where(HrefCellLine.line_id == line, HrefCellLine.cell_id == cell)).scalar_one_or_none():
        raise HTTPException(status_code=422, detail="Cell is not assigned to the selected line")


@app.get("/production-ingest-clients/{client_id}", response_model=ProductionIngestClientRead)
def get_production_ingest_client_endpoint(
    client_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current=Depends(require_permission("production.admin")),
):
    user, _session_row = current
    tenant_id = require_tenant_access(request, user, db)
    row = get_production_ingest_client(db, client_id, tenant_id=tenant_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Production ingest client not found")
    return _serialize_production_ingest_client(row)


@app.post("/production-ingest-clients", response_model=ProductionIngestClientRead, status_code=status.HTTP_201_CREATED)
def create_production_ingest_client_endpoint(
    payload: ProductionIngestClientCreate,
    request: Request,
    db: Session = Depends(get_db),
    current=Depends(require_permission("production.admin")),
):
    _user, session_row = current
    require_csrf(request, session_row)
    tenant_id = require_tenant_access(request, _user, db)
    _validate_ingest_client_context(db, tenant_id, payload.plant_code, payload.line_code, payload.machine_code)
    client = ProductionIngestClient(
        client_id=payload.client_id,
        description=payload.description,
        api_key_hash=hash_password(payload.api_key),
        plant_code=payload.plant_code,
        line_code=payload.line_code,
        station_code=payload.station_code,
        machine_code=payload.machine_code,
        source_system=payload.source_system,
        is_active=payload.is_active,
        tenant_id=tenant_id,
    )
    try:
        row = create_production_ingest_client(db, client)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Production ingest client already exists")
    return _serialize_production_ingest_client(row)


@app.patch("/production-ingest-clients/{client_id}", response_model=ProductionIngestClientRead)
def update_production_ingest_client_endpoint(
    client_id: str,
    payload: ProductionIngestClientUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current=Depends(require_permission("production.admin")),
):
    _user, session_row = current
    require_csrf(request, session_row)
    tenant_id = require_tenant_access(request, _user, db)
    row = get_production_ingest_client(db, client_id, tenant_id=tenant_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Production ingest client not found")
    updates = payload.model_dump(exclude_unset=True)
    _validate_ingest_client_context(db, tenant_id, updates.get("plant_code", row.plant_code), updates.get("line_code", row.line_code), updates.get("machine_code", row.machine_code))
    api_key = updates.pop("api_key", None)
    for field, value in updates.items():
        setattr(row, field, value)
    if api_key is not None:
        row.api_key_hash = hash_password(api_key)
    try:
        row = update_production_ingest_client(db, row)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Update conflict")
    return _serialize_production_ingest_client(row)


@app.delete("/production-ingest-clients/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_production_ingest_client_endpoint(
    client_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current=Depends(require_permission("production.admin")),
):
    _user, session_row = current
    require_csrf(request, session_row)
    tenant_id = require_tenant_access(request, _user, db)
    row = get_production_ingest_client(db, client_id, tenant_id=tenant_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Production ingest client not found")
    delete_production_ingest_client(db, row)
    return None


@app.get("/integration-servers", response_model=list[IntegrationServerRead])
def list_integration_servers_endpoint(request: Request, db: Session = Depends(get_db), current=Depends(require_permission("production.admin"))):
    user, _session = current
    tenant_id = require_tenant_access(request, user, db)
    rows = db.execute(select(IntegrationServer).where(IntegrationServer.tenant_id == tenant_id).order_by(IntegrationServer.server_id)).scalars().all()
    return [_serialize_integration_server(row) for row in rows]


@app.post("/integration-servers", response_model=IntegrationServerRead, status_code=status.HTTP_201_CREATED)
def create_integration_server_endpoint(payload: IntegrationServerCreate, request: Request, db: Session = Depends(get_db), current=Depends(require_permission("production.admin"))):
    user, session_row = current
    require_csrf(request, session_row)
    values = _apply_integration_server_credentials(payload.model_dump())
    row = IntegrationServer(tenant_id=require_tenant_access(request, user, db), **values)
    try:
        db.add(row); db.commit(); db.refresh(row)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Integration server already exists")
    return _serialize_integration_server(row)


@app.patch("/integration-servers/{server_id}", response_model=IntegrationServerRead)
def update_integration_server_endpoint(server_id: str, payload: IntegrationServerUpdate, request: Request, db: Session = Depends(get_db), current=Depends(require_permission("production.admin"))):
    user, session_row = current
    require_csrf(request, session_row)
    tenant_id = require_tenant_access(request, user, db)
    row = db.execute(select(IntegrationServer).where(IntegrationServer.tenant_id == tenant_id, IntegrationServer.server_id == server_id)).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration server not found")
    updates = _apply_integration_server_credentials(payload.model_dump(exclude_unset=True))
    for field, value in updates.items():
        setattr(row, field, value)
    db.commit(); db.refresh(row)
    return _serialize_integration_server(row)


@app.post("/integration-servers/{server_id}/test")
def test_integration_server_endpoint(server_id: str, request: Request, db: Session = Depends(get_db), current=Depends(require_permission("production.admin"))):
    user, session_row = current
    require_csrf(request, session_row)
    tenant_id = require_tenant_access(request, user, db)
    row = db.execute(select(IntegrationServer).where(IntegrationServer.tenant_id == tenant_id, IntegrationServer.server_id == server_id)).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration server not found")
    expires_in = _test_oauth_client_credentials(row)
    return {"ok": True, "message": "OAuth token obtained successfully", "expires_in": expires_in}


@app.delete("/integration-servers/{server_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_integration_server_endpoint(server_id: str, request: Request, db: Session = Depends(get_db), current=Depends(require_permission("production.admin"))):
    user, session_row = current
    require_csrf(request, session_row)
    tenant_id = require_tenant_access(request, user, db)
    row = db.execute(select(IntegrationServer).where(IntegrationServer.tenant_id == tenant_id, IntegrationServer.server_id == server_id)).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration server not found")
    if db.execute(select(IntegrationDeliveryRule.id).where(IntegrationDeliveryRule.server_id == row.id).limit(1)).scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Integration server is used by a delivery rule")
    db.delete(row); db.commit()
    return None


@app.get("/integration-delivery-rules", response_model=list[IntegrationDeliveryRuleRead])
def list_integration_delivery_rules_endpoint(request: Request, db: Session = Depends(get_db), current=Depends(require_permission("production.admin"))):
    user, _session = current
    tenant_id = require_tenant_access(request, user, db)
    rows = db.execute(select(IntegrationDeliveryRule, IntegrationServer).join(IntegrationServer, IntegrationDeliveryRule.server_id == IntegrationServer.id).where(IntegrationDeliveryRule.tenant_id == tenant_id).order_by(IntegrationDeliveryRule.rule_id)).all()
    return [_serialize_integration_delivery_rule(rule, server) for rule, server in rows]


@app.post("/integration-delivery-rules", response_model=IntegrationDeliveryRuleRead, status_code=status.HTTP_201_CREATED)
def create_integration_delivery_rule_endpoint(payload: IntegrationDeliveryRuleCreate, request: Request, db: Session = Depends(get_db), current=Depends(require_permission("production.admin"))):
    user, session_row = current
    require_csrf(request, session_row)
    tenant_id = require_tenant_access(request, user, db)
    server = db.execute(select(IntegrationServer).where(IntegrationServer.id == payload.server_id, IntegrationServer.tenant_id == tenant_id)).scalar_one_or_none()
    if not server:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration server not found")
    row = IntegrationDeliveryRule(tenant_id=tenant_id, **payload.model_dump())
    try:
        db.add(row); db.commit(); db.refresh(row)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Integration delivery rule already exists")
    return _serialize_integration_delivery_rule(row, server)


@app.patch("/integration-delivery-rules/{rule_id}", response_model=IntegrationDeliveryRuleRead)
def update_integration_delivery_rule_endpoint(rule_id: str, payload: IntegrationDeliveryRuleUpdate, request: Request, db: Session = Depends(get_db), current=Depends(require_permission("production.admin"))):
    user, session_row = current
    require_csrf(request, session_row)
    tenant_id = require_tenant_access(request, user, db)
    row = db.execute(select(IntegrationDeliveryRule).where(IntegrationDeliveryRule.tenant_id == tenant_id, IntegrationDeliveryRule.rule_id == rule_id)).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration delivery rule not found")
    updates = payload.model_dump(exclude_unset=True)
    if "server_id" in updates:
        server = db.execute(select(IntegrationServer).where(IntegrationServer.id == updates["server_id"], IntegrationServer.tenant_id == tenant_id)).scalar_one_or_none()
        if not server:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration server not found")
    for field, value in updates.items():
        setattr(row, field, value)
    db.commit(); db.refresh(row)
    server = db.get(IntegrationServer, row.server_id)
    return _serialize_integration_delivery_rule(row, server)


@app.delete("/integration-delivery-rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_integration_delivery_rule_endpoint(rule_id: str, request: Request, db: Session = Depends(get_db), current=Depends(require_permission("production.admin"))):
    user, session_row = current
    require_csrf(request, session_row)
    tenant_id = require_tenant_access(request, user, db)
    row = db.execute(select(IntegrationDeliveryRule).where(IntegrationDeliveryRule.tenant_id == tenant_id, IntegrationDeliveryRule.rule_id == rule_id)).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration delivery rule not found")
    db.delete(row); db.commit()
    return None


@app.post("/production-reports", response_model=ProductionReportRead, status_code=status.HTTP_201_CREATED)
def create_production_report_endpoint(
    payload: ProductionReportCreate,
    request: Request,
    db: Session = Depends(get_db),
    current=Depends(require_permission("production.write")),
):
    user, session_row = current
    require_csrf(request, session_row)
    tenant_id = require_tenant_access(request, user, db)
    report = ProductionReport(**payload.model_dump(), tenant_id=tenant_id)
    try:
        row = create_production_report(db, report)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Production report already exists or data invalid")
    return _serialize_production_report(row)


@app.post("/production-reports/ingest", response_model=ProductionReportRead, status_code=status.HTTP_201_CREATED)
def ingest_production_report_endpoint(
    payload: ProductionReportIngestCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    client = require_production_ingest_api_key(request, db)
    values = payload.model_dump()
    if client is not None:
        for field in ("plant_code", "line_code", "station_code", "machine_code", "source_system"):
            configured = getattr(client, field)
            if configured:
                values[field] = configured
    values = ProductionReportCreate.model_validate(values).model_dump()
    report = ProductionReport(**values, tenant_id=client.tenant_id if client is not None else get_default_tenant_id())
    try:
        row = create_production_report(db, report)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Production report already exists or data invalid")
    return _serialize_production_report(row)


@app.post("/stoppage-events/ingest", response_model=StoppageBatchIngestResult)
def ingest_stoppage_events_endpoint(payload: StoppageBatchIngest, request: Request, db: Session = Depends(get_db)):
    """Upsert Edge downtime events. Replays are safe and required for OT recovery."""
    client = require_production_ingest_api_key(request, db)
    tenant_id = client.tenant_id if client is not None else get_default_tenant_id()
    inserted = updated = 0
    for item in payload.events:
        if client is not None and client.line_code and item.line_id != client.line_code:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Line scope mismatch")
        row = db.execute(select(StoppageEvent).where(
            StoppageEvent.tenant_id == tenant_id,
            StoppageEvent.source_event_id == item.source_event_id,
        )).scalar_one_or_none()
        values = item.model_dump()
        if row is None:
            db.add(StoppageEvent(**values, tenant_id=tenant_id))
            inserted += 1
        elif item.edge_updated_at >= row.edge_updated_at:
            for field, value in values.items():
                setattr(row, field, value)
            updated += 1
    db.commit()
    return StoppageBatchIngestResult(accepted=len(payload.events), inserted=inserted, updated=updated)


@app.get("/production-reports/analytics/daily-total", response_model=list[DailyProductionTotalRead])
def production_daily_total_endpoint(
    request: Request,
    date_from: str | None = None,
    date_to: str | None = None,
    plant_code: str | None = None,
    line_code: str | None = None,
    db: Session = Depends(get_db),
    current=Depends(require_permission("production.read")),
):
    user, _session_row = current
    tenant_id = require_tenant_access(request, user, db)
    rows = get_daily_totals(
        db,
        tenant_id=tenant_id,
        date_from=_parse_datetime_filter(date_from),
        date_to=_parse_datetime_filter(date_to, end_of_day=True),
        plant_code=plant_code,
        line_code=line_code,
    )
    return [
        DailyProductionTotalRead(
            production_day=_coerce_date(row.production_day),
            total_production=row.total_production,
        )
        for row in rows
    ]


@app.get("/production-reports/analytics/by-line", response_model=list[ProductionByLineRead])
def production_by_line_endpoint(
    request: Request,
    date_from: str | None = None,
    date_to: str | None = None,
    plant_code: str | None = None,
    db: Session = Depends(get_db),
    current=Depends(require_permission("production.read")),
):
    user, _session_row = current
    tenant_id = require_tenant_access(request, user, db)
    rows = get_production_by_line(
        db,
        tenant_id=tenant_id,
        date_from=_parse_datetime_filter(date_from),
        date_to=_parse_datetime_filter(date_to, end_of_day=True),
        plant_code=plant_code,
    )
    return [ProductionByLineRead(line_code=row.line_code, total_production=row.total_production) for row in rows]


@app.get("/production-reports/analytics/ok-nok-by-shift", response_model=list[OkNokByShiftRead])
def ok_nok_by_shift_endpoint(
    request: Request,
    date_from: str | None = None,
    date_to: str | None = None,
    plant_code: str | None = None,
    line_code: str | None = None,
    db: Session = Depends(get_db),
    current=Depends(require_permission("production.read")),
):
    user, _session_row = current
    tenant_id = require_tenant_access(request, user, db)
    rows = get_ok_nok_by_shift(
        db,
        tenant_id=tenant_id,
        date_from=_parse_datetime_filter(date_from),
        date_to=_parse_datetime_filter(date_to, end_of_day=True),
        plant_code=plant_code,
        line_code=line_code,
    )
    return [
        OkNokByShiftRead(
            shift_code=row.shift_code,
            ok_count=row.ok_count,
            nok_count=row.nok_count,
            scrap_count=row.scrap_count,
            rework_count=row.rework_count,
        )
        for row in rows
    ]


@app.get("/production-reports/analytics/ftq-fpy", response_model=list[FtqFpyRead])
def ftq_fpy_endpoint(
    request: Request,
    date_from: str | None = None,
    date_to: str | None = None,
    plant_code: str | None = None,
    line_code: str | None = None,
    db: Session = Depends(get_db),
    current=Depends(require_permission("production.read")),
):
    user, _session_row = current
    tenant_id = require_tenant_access(request, user, db)
    rows = get_ftq_fpy_by_line_and_day(
        db,
        tenant_id=tenant_id,
        date_from=_parse_datetime_filter(date_from),
        date_to=_parse_datetime_filter(date_to, end_of_day=True),
        plant_code=plant_code,
        line_code=line_code,
    )
    return [
        FtqFpyRead(
            production_day=_coerce_date(row.production_day),
            line_code=row.line_code,
            first_pass_total=row.first_pass_total,
            first_pass_ok=row.first_pass_ok,
            ftq_percent=round((row.first_pass_ok / row.first_pass_total) * 100, 2) if row.first_pass_total else 0.0,
            serial_total=row.serial_total,
            serial_ok=row.serial_ok,
            fpy_percent=round((row.serial_ok / row.serial_total) * 100, 2) if row.serial_total else 0.0,
        )
        for row in rows
    ]


@app.get("/production-reports/analytics/top-defects", response_model=list[TopDefectRead])
def top_defects_endpoint(
    request: Request,
    date_from: str | None = None,
    date_to: str | None = None,
    plant_code: str | None = None,
    line_code: str | None = None,
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    current=Depends(require_permission("production.read")),
):
    user, _session_row = current
    tenant_id = require_tenant_access(request, user, db)
    rows = get_top_defects(
        db,
        tenant_id=tenant_id,
        date_from=_parse_datetime_filter(date_from),
        date_to=_parse_datetime_filter(date_to, end_of_day=True),
        plant_code=plant_code,
        line_code=line_code,
        limit=limit,
    )
    return [
        TopDefectRead(
            error_code=row.error_code,
            error_description=row.error_description,
            defect_count=row.defect_count,
        )
        for row in rows
    ]


@app.get("/production-reports/traceability/{serial_number}", response_model=list[ProductionReportRead])
def traceability_by_serial_endpoint(
    serial_number: str,
    request: Request,
    db: Session = Depends(get_db),
    current=Depends(require_permission("production.read")),
):
    user, _session_row = current
    tenant_id = require_tenant_access(request, user, db)
    rows = get_traceability(db, serial_number, tenant_id=tenant_id)
    return [_serialize_production_report(row) for row in rows]


@app.get("/production-reports/analytics/average-cycle-time", response_model=list[AverageCycleTimeByLineRead])
def average_cycle_time_by_line_endpoint(
    request: Request,
    date_from: str | None = None,
    date_to: str | None = None,
    plant_code: str | None = None,
    db: Session = Depends(get_db),
    current=Depends(require_permission("production.read")),
):
    user, _session_row = current
    tenant_id = require_tenant_access(request, user, db)
    rows = get_average_cycle_time_by_line(
        db,
        tenant_id=tenant_id,
        date_from=_parse_datetime_filter(date_from),
        date_to=_parse_datetime_filter(date_to, end_of_day=True),
        plant_code=plant_code,
    )
    return [
        AverageCycleTimeByLineRead(
            line_code=row.line_code,
            average_cycle_time_seconds=round(float(row.average_cycle_time_seconds), 3),
            sample_count=row.sample_count,
        )
        for row in rows
    ]


@app.get("/production-reports/{report_id}", response_model=ProductionReportRead)
def get_production_report_endpoint(
    report_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current=Depends(require_permission("production.read")),
):
    user, _session_row = current
    tenant_id = require_tenant_access(request, user, db)
    row = get_production_report(db, report_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Production report not found")
    if row.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Production report not found")
    return _serialize_production_report(row)


@app.get("/statuses", response_model=list[StatusRead])
def statuses(request: Request, db: Session = Depends(get_db), current=Depends(require_permission("masters.read"))):
    user, _session_row = current
    tenant_id = require_tenant_access(request, user, db)
    rows = list_statuses(db, tenant_id=tenant_id)
    return [StatusRead(status_id=row.status_id, description_status=row.description_status) for row in rows]

@app.get("/statuses/{status_id}", response_model=StatusRead)
def get_status_endpoint(status_id: str, request: Request, db: Session = Depends(get_db), current=Depends(require_permission("masters.read"))):
    user, _session_row = current
    tenant_id = require_tenant_access(request, user, db)
    row = get_status(db, status_id, tenant_id=tenant_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Status not found")
    return StatusRead(status_id=row.status_id, description_status=row.description_status)


@app.post("/statuses", response_model=StatusRead, status_code=status.HTTP_201_CREATED)
def create_status_endpoint(payload: StatusCreate, request: Request, db: Session = Depends(get_db), current=Depends(require_permission("masters.write"))):
    user, session_row = current
    require_csrf(request, session_row)
    tenant_id = require_tenant_access(request, user, db)
    status_row = TbStatus(status_id=payload.status_id, description_status=payload.description_status, tenant_id=tenant_id)
    try:
        row = create_status(db, status_row)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Status already exists")
    return StatusRead(status_id=row.status_id, description_status=row.description_status)


@app.patch("/statuses/{status_id}", response_model=StatusRead)
def update_status(status_id: str, payload: StatusUpdate, request: Request, db: Session = Depends(get_db), current=Depends(require_permission("masters.write"))):
    user, session_row = current
    require_csrf(request, session_row)
    tenant_id = require_tenant_access(request, user, db)
    row = get_status(db, status_id, tenant_id=tenant_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Status not found")
    if payload.description_status is not None:
        row.description_status = payload.description_status
    try:
        db.commit()
        db.refresh(row)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Update conflict")
    return StatusRead(status_id=row.status_id, description_status=row.description_status)


@app.delete("/statuses/{status_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_status_endpoint(status_id: str, request: Request, db: Session = Depends(get_db), current=Depends(require_permission("masters.write"))):
    user, session_row = current
    require_csrf(request, session_row)
    tenant_id = require_tenant_access(request, user, db)
    row = get_status(db, status_id, tenant_id=tenant_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Status not found")
    delete_status(db, row)
    return None


@app.get("/lines", response_model=list[LineRead])
def lines(request: Request, db: Session = Depends(get_db), current=Depends(require_permission("masters.read"))):
    user, _session_row = current
    tenant_id = require_tenant_access(request, user, db)
    rows = list_lines(db, tenant_id=tenant_id)
    return [LineRead(line_id=row.line_id, description_line=row.description_line, create_date=row.create_date) for row in rows]


@app.get("/plants", response_model=list[PlantRead])
def plants(request: Request, db: Session = Depends(get_db), current=Depends(require_permission("masters.read"))):
    user, _session_row = current
    tenant_id = require_tenant_access(request, user, db)
    rows = db.execute(
        select(TbPlants).where(TbPlants.tenant_id == tenant_id).order_by(TbPlants.plant_id)
    ).scalars().all()
    return [PlantRead(plant_id=row.plant_id, description_plant=row.description_plant, create_date=row.create_date) for row in rows]


@app.post("/plants", response_model=PlantRead, status_code=status.HTTP_201_CREATED)
def create_plant_endpoint(payload: PlantCreate, request: Request, db: Session = Depends(get_db), current=Depends(require_permission("masters.write"))):
    user, session_row = current
    require_csrf(request, session_row)
    tenant_id = require_tenant_access(request, user, db)
    row = TbPlants(plant_id=payload.plant_id, description_plant=payload.description_plant, tenant_id=tenant_id)
    try:
        db.add(row)
        db.commit()
        db.refresh(row)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Plant already exists")
    return PlantRead(plant_id=row.plant_id, description_plant=row.description_plant, create_date=row.create_date)


@app.patch("/plants/{plant_id}", response_model=PlantRead)
def update_plant_endpoint(plant_id: str, payload: PlantUpdate, request: Request, db: Session = Depends(get_db), current=Depends(require_permission("masters.write"))):
    user, session_row = current
    require_csrf(request, session_row)
    tenant_id = require_tenant_access(request, user, db)
    row = db.execute(select(TbPlants).where(TbPlants.tenant_id == tenant_id, TbPlants.plant_id == plant_id)).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plant not found")
    if payload.description_plant is not None:
        row.description_plant = payload.description_plant
    db.commit()
    db.refresh(row)
    return PlantRead(plant_id=row.plant_id, description_plant=row.description_plant, create_date=row.create_date)


@app.delete("/plants/{plant_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_plant_endpoint(plant_id: str, request: Request, db: Session = Depends(get_db), current=Depends(require_permission("masters.write"))):
    user, session_row = current
    require_csrf(request, session_row)
    tenant_id = require_tenant_access(request, user, db)
    row = db.execute(select(TbPlants).where(TbPlants.tenant_id == tenant_id, TbPlants.plant_id == plant_id)).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plant not found")
    in_use = db.execute(
        select(ProductionIngestClient.id).where(
            ProductionIngestClient.tenant_id == tenant_id,
            ProductionIngestClient.plant_code == plant_id,
        ).limit(1)
    ).scalar_one_or_none()
    if in_use:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Plant is used by an integration client")
    db.delete(row)
    db.commit()
    return None


@app.get("/lines/{line_id}", response_model=LineRead)
def get_line_endpoint(line_id: str, request: Request, db: Session = Depends(get_db), current=Depends(require_permission("masters.read"))):
    user, _session_row = current
    tenant_id = require_tenant_access(request, user, db)
    row = get_line(db, line_id, tenant_id=tenant_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Line not found")
    return LineRead(line_id=row.line_id, description_line=row.description_line, create_date=row.create_date)


@app.post("/lines", response_model=LineRead, status_code=status.HTTP_201_CREATED)
def create_line_endpoint(payload: LineCreate, request: Request, db: Session = Depends(get_db), current=Depends(require_permission("masters.write"))):
    user, session_row = current
    require_csrf(request, session_row)
    tenant_id = require_tenant_access(request, user, db)
    line = TbLines(line_id=payload.line_id, description_line=payload.description_line, tenant_id=tenant_id)
    try:
        row = create_line(db, line)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Line already exists")
    return LineRead(line_id=row.line_id, description_line=row.description_line, create_date=row.create_date)


@app.patch("/lines/{line_id}", response_model=LineRead)
def update_line_endpoint(line_id: str, payload: LineUpdate, request: Request, db: Session = Depends(get_db), current=Depends(require_permission("masters.write"))):
    user, session_row = current
    require_csrf(request, session_row)
    tenant_id = require_tenant_access(request, user, db)
    row = get_line(db, line_id, tenant_id=tenant_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Line not found")
    if payload.description_line is not None:
        row.description_line = payload.description_line
    try:
        row = update_line(db, row)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Update conflict")
    return LineRead(line_id=row.line_id, description_line=row.description_line, create_date=row.create_date)


@app.delete("/lines/{line_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_line_endpoint(line_id: str, request: Request, db: Session = Depends(get_db), current=Depends(require_permission("masters.write"))):
    user, session_row = current
    require_csrf(request, session_row)
    tenant_id = require_tenant_access(request, user, db)
    row = get_line(db, line_id, tenant_id=tenant_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Line not found")
    delete_line(db, row)
    return None


@app.get("/cells", response_model=list[CellRead])
def cells(request: Request, db: Session = Depends(get_db), current=Depends(require_permission("masters.read"))):
    user, _session_row = current
    tenant_id = require_tenant_access(request, user, db)
    rows = list_cells(db, tenant_id=tenant_id)
    return [CellRead(cell_id=row.cell_id, description_cell=row.description_cell, create_date=row.create_date) for row in rows]


@app.get("/cells/{cell_id}/lines", response_model=list[LineRead])
def get_cell_lines_endpoint(cell_id: str, request: Request, db: Session = Depends(get_db), current=Depends(require_permission("masters.read"))):
    user, _session_row = current
    tenant_id = require_tenant_access(request, user, db)
    cell = db.execute(select(TbCells).where(TbCells.tenant_id == tenant_id, TbCells.cell_id == cell_id)).scalar_one_or_none()
    if not cell:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cell not found")
    rows = db.execute(
        select(TbLines)
        .join(HrefCellLine, HrefCellLine.line_id == TbLines.line_id)
        .where(TbLines.tenant_id == tenant_id, HrefCellLine.cell_id == cell_id)
        .order_by(TbLines.line_id)
    ).scalars().all()
    return [LineRead(line_id=row.line_id, description_line=row.description_line, create_date=row.create_date) for row in rows]


@app.put("/cells/{cell_id}/lines", response_model=list[LineRead])
def replace_cell_lines_endpoint(cell_id: str, payload: CellLineAssignmentUpdate, request: Request, db: Session = Depends(get_db), current=Depends(require_permission("masters.write"))):
    user, session_row = current
    require_csrf(request, session_row)
    tenant_id = require_tenant_access(request, user, db)
    cell = db.execute(select(TbCells).where(TbCells.tenant_id == tenant_id, TbCells.cell_id == cell_id)).scalar_one_or_none()
    if not cell:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cell not found")
    requested_line_ids = sorted(set(payload.line_ids))
    valid_line_ids = set(db.execute(select(TbLines.line_id).where(TbLines.tenant_id == tenant_id, TbLines.line_id.in_(requested_line_ids))).scalars().all()) if requested_line_ids else set()
    if len(valid_line_ids) != len(requested_line_ids):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="One or more lines do not belong to the active tenant")
    current_line_ids = set(db.execute(select(HrefCellLine.line_id).where(HrefCellLine.cell_id == cell_id)).scalars().all())
    removed_line_ids = current_line_ids - valid_line_ids
    if removed_line_ids and db.execute(
        select(ProductionIngestClient.id).where(
            ProductionIngestClient.tenant_id == tenant_id,
            ProductionIngestClient.machine_code == cell_id,
            ProductionIngestClient.line_code.in_(removed_line_ids),
        ).limit(1)
    ).scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A client uses this cell-line assignment")
    db.query(HrefCellLine).filter(HrefCellLine.cell_id == cell_id).delete(synchronize_session=False)
    db.add_all([HrefCellLine(cell_id=cell_id, line_id=line_id) for line_id in requested_line_ids])
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cell-line assignment conflict")
    rows = db.execute(select(TbLines).where(TbLines.tenant_id == tenant_id, TbLines.line_id.in_(requested_line_ids)).order_by(TbLines.line_id)).scalars().all() if requested_line_ids else []
    return [LineRead(line_id=row.line_id, description_line=row.description_line, create_date=row.create_date) for row in rows]


@app.get("/cells/{cell_id}", response_model=CellRead)
def get_cell_endpoint(cell_id: str, request: Request, db: Session = Depends(get_db), current=Depends(require_permission("masters.read"))):
    user, _session_row = current
    tenant_id = require_tenant_access(request, user, db)
    row = get_cell(db, cell_id, tenant_id=tenant_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cell not found")
    return CellRead(cell_id=row.cell_id, description_cell=row.description_cell, create_date=row.create_date)


@app.post("/cells", response_model=CellRead, status_code=status.HTTP_201_CREATED)
def create_cell_endpoint(payload: CellCreate, request: Request, db: Session = Depends(get_db), current=Depends(require_permission("masters.write"))):
    user, session_row = current
    require_csrf(request, session_row)
    tenant_id = require_tenant_access(request, user, db)
    cell = TbCells(cell_id=payload.cell_id, description_cell=payload.description_cell, tenant_id=tenant_id)
    try:
        row = create_cell(db, cell)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cell already exists")
    return CellRead(cell_id=row.cell_id, description_cell=row.description_cell, create_date=row.create_date)


@app.patch("/cells/{cell_id}", response_model=CellRead)
def update_cell_endpoint(cell_id: str, payload: CellUpdate, request: Request, db: Session = Depends(get_db), current=Depends(require_permission("masters.write"))):
    user, session_row = current
    require_csrf(request, session_row)
    tenant_id = require_tenant_access(request, user, db)
    row = get_cell(db, cell_id, tenant_id=tenant_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cell not found")
    if payload.description_cell is not None:
        row.description_cell = payload.description_cell
    try:
        row = update_cell(db, row)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Update conflict")
    return CellRead(cell_id=row.cell_id, description_cell=row.description_cell, create_date=row.create_date)


@app.delete("/cells/{cell_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_cell_endpoint(cell_id: str, request: Request, db: Session = Depends(get_db), current=Depends(require_permission("masters.write"))):
    user, session_row = current
    require_csrf(request, session_row)
    tenant_id = require_tenant_access(request, user, db)
    row = get_cell(db, cell_id, tenant_id=tenant_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cell not found")
    delete_cell(db, row)
    return None


@app.get("/models", response_model=list[ModelRead])
def models(request: Request, db: Session = Depends(get_db), current=Depends(require_permission("masters.read"))):
    user, _session_row = current
    tenant_id = require_tenant_access(request, user, db)
    rows = list_models(db, tenant_id=tenant_id)
    return [ModelRead(model_id=row.model_id, description_model=row.description_model, create_date=row.create_date) for row in rows]


@app.get("/models/{model_id}", response_model=ModelRead)
def get_model_endpoint(model_id: str, request: Request, db: Session = Depends(get_db), current=Depends(require_permission("masters.read"))):
    user, _session_row = current
    tenant_id = require_tenant_access(request, user, db)
    row = get_model(db, model_id, tenant_id=tenant_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model not found")
    return ModelRead(model_id=row.model_id, description_model=row.description_model, create_date=row.create_date)


@app.post("/models", response_model=ModelRead, status_code=status.HTTP_201_CREATED)
def create_model_endpoint(payload: ModelCreate, request: Request, db: Session = Depends(get_db), current=Depends(require_permission("masters.write"))):
    user, session_row = current
    require_csrf(request, session_row)
    tenant_id = require_tenant_access(request, user, db)
    model = TbModels(model_id=payload.model_id, description_model=payload.description_model, tenant_id=tenant_id)
    try:
        row = create_model(db, model)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Model already exists")
    return ModelRead(model_id=row.model_id, description_model=row.description_model, create_date=row.create_date)


@app.patch("/models/{model_id}", response_model=ModelRead)
def update_model_endpoint(model_id: str, payload: ModelUpdate, request: Request, db: Session = Depends(get_db), current=Depends(require_permission("masters.write"))):
    user, session_row = current
    require_csrf(request, session_row)
    tenant_id = require_tenant_access(request, user, db)
    row = get_model(db, model_id, tenant_id=tenant_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model not found")
    if payload.description_model is not None:
        row.description_model = payload.description_model
    try:
        row = update_model(db, row)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Update conflict")
    return ModelRead(model_id=row.model_id, description_model=row.description_model, create_date=row.create_date)


@app.delete("/models/{model_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_model_endpoint(model_id: str, request: Request, db: Session = Depends(get_db), current=Depends(require_permission("masters.write"))):
    user, session_row = current
    require_csrf(request, session_row)
    tenant_id = require_tenant_access(request, user, db)
    row = get_model(db, model_id, tenant_id=tenant_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model not found")
    delete_model(db, row)
    return None

@app.get("/items", response_model=list[ItemRead])
def items(
    request: Request,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    status_id: str | None = None,
    line_id: str | None = None,
    model_id: str | None = None,
    cell_id: str | None = None,
    id_user: str | None = None,
    create_date_from: str | None = None,
    create_date_to: str | None = None,
    last_test_date_from: str | None = None,
    last_test_date_to: str | None = None,
    db: Session = Depends(get_db),
    current=Depends(require_permission("items.read")),
):
    user, _session_row = current
    tenant_id = require_tenant_access(request, user, db)
    def _parse_date(value: str | None, end_of_day: bool = False):
        if not value:
            return None
        try:
            if len(value) == 10:
                parsed = date.fromisoformat(value)
                return datetime.combine(parsed, time.max if end_of_day else time.min)
            return datetime.fromisoformat(value)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid date format")

    rows = list_items(
        db,
        tenant_id=tenant_id,
        limit=limit,
        offset=offset,
        status_id=status_id,
        line_id=line_id,
        model_id=model_id,
        cell_id=cell_id,
        id_user=id_user,
        create_date_from=_parse_date(create_date_from),
        create_date_to=_parse_date(create_date_to, end_of_day=True),
        last_test_date_from=_parse_date(last_test_date_from),
        last_test_date_to=_parse_date(last_test_date_to, end_of_day=True),
    )
    return [
        ItemRead(
            item_id=row.item_id,
            model_id=row.model_id,
            line_id=row.line_id,
            location_id=row.location_id,
            cell_id=row.cell_id,
            id_user=row.id_user,
            status_id=row.status_id,
            create_date=row.create_date,
            last_test_date=row.last_test_date,
            value1_int=row.value1_int,
            value2_int=row.value2_int,
            value3_int=row.value3_int,
            value4_int=row.value4_int,
            value5_int=row.value5_int,
            value1_str=row.value1_str,
            value2_str=row.value2_str,
            value3_str=row.value3_str,
            value4_str=row.value4_str,
            value5_str=row.value5_str,
        )
        for row in rows
    ]


@app.post("/items", response_model=ItemRead, status_code=status.HTTP_201_CREATED)
def create_item_endpoint(payload: ItemCreate, request: Request, db: Session = Depends(get_db), current=Depends(require_permission("items.write"))):
    user, session_row = current
    require_csrf(request, session_row)
    tenant_id = require_tenant_access(request, user, db)
    item = TbItems(
        item_id=payload.item_id,
        model_id=payload.model_id,
        line_id=payload.line_id,
        location_id=payload.location_id,
        cell_id=payload.cell_id,
        id_user=payload.id_user,
        status_id=payload.status_id,
        value1_int=payload.value1_int,
        value2_int=payload.value2_int,
        value3_int=payload.value3_int,
        value4_int=payload.value4_int,
        value5_int=payload.value5_int,
        value1_str=payload.value1_str,
        value2_str=payload.value2_str,
        value3_str=payload.value3_str,
        value4_str=payload.value4_str,
        value5_str=payload.value5_str,
        tenant_id=tenant_id,
    )
    try:
        row = create_item(db, item)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Item already exists or FK invalid")
    return ItemRead(
        item_id=row.item_id,
        model_id=row.model_id,
        line_id=row.line_id,
        location_id=row.location_id,
        cell_id=row.cell_id,
        id_user=row.id_user,
        status_id=row.status_id,
        create_date=row.create_date,
        last_test_date=row.last_test_date,
        value1_int=row.value1_int,
        value2_int=row.value2_int,
        value3_int=row.value3_int,
        value4_int=row.value4_int,
        value5_int=row.value5_int,
        value1_str=row.value1_str,
        value2_str=row.value2_str,
        value3_str=row.value3_str,
        value4_str=row.value4_str,
        value5_str=row.value5_str,
    )

@app.get("/items/{item_id}", response_model=ItemRead)
def get_item_endpoint(item_id: str, request: Request, db: Session = Depends(get_db), current=Depends(require_permission("items.read"))):
    user, _session_row = current
    tenant_id = require_tenant_access(request, user, db)
    row = get_item(db, item_id, tenant_id=tenant_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
    return ItemRead(
        item_id=row.item_id,
        model_id=row.model_id,
        line_id=row.line_id,
        location_id=row.location_id,
        cell_id=row.cell_id,
        id_user=row.id_user,
        status_id=row.status_id,
        create_date=row.create_date,
        last_test_date=row.last_test_date,
        value1_int=row.value1_int,
        value2_int=row.value2_int,
        value3_int=row.value3_int,
        value4_int=row.value4_int,
        value5_int=row.value5_int,
        value1_str=row.value1_str,
        value2_str=row.value2_str,
        value3_str=row.value3_str,
        value4_str=row.value4_str,
        value5_str=row.value5_str,
    )


@app.patch("/items/{item_id}", response_model=ItemRead)
def update_item_endpoint(item_id: str, payload: ItemUpdate, request: Request, db: Session = Depends(get_db), current=Depends(require_permission("items.write"))):
    user, session_row = current
    require_csrf(request, session_row)
    tenant_id = require_tenant_access(request, user, db)
    row = get_item(db, item_id, tenant_id=tenant_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    try:
        row = update_item(db, row)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Update conflict")
    return ItemRead(
        item_id=row.item_id,
        model_id=row.model_id,
        line_id=row.line_id,
        location_id=row.location_id,
        cell_id=row.cell_id,
        id_user=row.id_user,
        status_id=row.status_id,
        create_date=row.create_date,
        last_test_date=row.last_test_date,
        value1_int=row.value1_int,
        value2_int=row.value2_int,
        value3_int=row.value3_int,
        value4_int=row.value4_int,
        value5_int=row.value5_int,
        value1_str=row.value1_str,
        value2_str=row.value2_str,
        value3_str=row.value3_str,
        value4_str=row.value4_str,
        value5_str=row.value5_str,
    )


@app.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item_endpoint(item_id: str, request: Request, db: Session = Depends(get_db), current=Depends(require_permission("items.write"))):
    user, session_row = current
    require_csrf(request, session_row)
    tenant_id = require_tenant_access(request, user, db)
    row = get_item(db, item_id, tenant_id=tenant_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
    delete_item(db, row)
    return None


@app.get("/users/me", response_model=UserRead)
def get_my_user_endpoint(
    request: Request,
    db: Session = Depends(get_db),
    current=Depends(get_current_session),
):
    user, _session_row = current
    require_tenant_access(request, user, db)
    return _serialize_user(db, user)


@app.patch("/users/me", response_model=UserRead)
def update_my_user_endpoint(
    payload: UserSelfUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current=Depends(get_current_session),
):
    user, session_row = current
    require_csrf(request, session_row)
    require_tenant_access(request, user, db)
    updates = payload.model_dump(exclude_unset=True)
    password = updates.pop("password", None)
    for field, value in updates.items():
        setattr(user, field, value)
    try:
        row = update_user(db, user, password)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Update conflict")
    return _serialize_user(db, row)

@app.get("/users", response_model=list[UserRead])
def users(
    request: Request,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    _perm=Depends(require_permission("users.read")),
    _admin=Depends(require_admin),
):
    tenant_id = require_tenant_access(request, _admin[0], db)
    rows = list_users(db, limit=limit, offset=offset, tenant_id=tenant_id)
    return [_serialize_user(db, row) for row in rows]


@app.get("/users/{id_user}", response_model=UserRead)
def get_user_endpoint(
    id_user: str, request: Request, db: Session = Depends(get_db), _perm=Depends(require_permission("users.read")), _admin=Depends(require_admin)
):
    tenant_id = require_tenant_access(request, _admin[0], db)
    row = get_user(db, id_user)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    accessible_tenant_ids = {tenant.tenant_id for tenant in list_user_tenants(db, row.id_user)}
    accessible_tenant_ids.add(row.tenant_id)
    if tenant_id not in accessible_tenant_ids:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return _serialize_user(db, row)


@app.post("/users", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user_endpoint(
    payload: UserCreate,
    request: Request,
    db: Session = Depends(get_db),
    current=Depends(require_permission("users.write")),
    _admin=Depends(require_admin),
):
    _user, session_row = current
    require_csrf(request, session_row)
    tenant_id = require_tenant_access(request, _user, db)
    accessible_tenant_ids = sorted(set(payload.accessible_tenant_ids or [tenant_id]) | {tenant_id})
    known_tenant_ids = {tenant.tenant_id for tenant in list_tenants(db)}
    unknown_tenants = [entry for entry in accessible_tenant_ids if entry not in known_tenant_ids]
    if unknown_tenants:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown tenants: {unknown_tenants}")
    user = TbUsers(
        id_user=payload.id_user,
        name_user=payload.name_user,
        mail_user=payload.mail_user,
        tenant_id=tenant_id,
        id_group=payload.id_group,
        status_user=payload.status_user,
        pass_hash="",
    )
    try:
        row = create_user(db, user, payload.password)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User already exists or FK invalid")
    replace_user_roles(db, row.id_user, ["USR"])
    replace_user_tenants(db, row.id_user, accessible_tenant_ids)
    return _serialize_user(db, row)

@app.patch("/users/{id_user}", response_model=UserRead)
def update_user_endpoint(
    id_user: str,
    payload: UserUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current=Depends(require_permission("users.write")),
    _admin=Depends(require_admin),
):
    _user, session_row = current
    require_csrf(request, session_row)
    tenant_id = require_tenant_access(request, _user, db)
    row = get_user(db, id_user)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    row_tenant_ids = {tenant.tenant_id for tenant in list_user_tenants(db, row.id_user)}
    row_tenant_ids.add(row.tenant_id)
    if tenant_id not in row_tenant_ids:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    updates = payload.model_dump(exclude_unset=True)
    accessible_tenant_ids = updates.pop("accessible_tenant_ids", None)
    if accessible_tenant_ids is not None:
        scoped_tenant_ids = sorted(set(accessible_tenant_ids or [row.tenant_id]) | {row.tenant_id})
        known_tenant_ids = {tenant.tenant_id for tenant in list_tenants(db)}
        unknown_tenants = [entry for entry in scoped_tenant_ids if entry not in known_tenant_ids]
        if unknown_tenants:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown tenants: {unknown_tenants}")
    password = updates.pop("password", None)
    for field, value in updates.items():
        setattr(row, field, value)
    try:
        row = update_user(db, row, password)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Update conflict")
    if accessible_tenant_ids is not None:
        replace_user_tenants(db, row.id_user, scoped_tenant_ids)
    return _serialize_user(db, row)


@app.delete("/users/{id_user}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user_endpoint(
    id_user: str,
    request: Request,
    db: Session = Depends(get_db),
    current=Depends(require_permission("users.write")),
    _admin=Depends(require_admin),
):
    _user, session_row = current
    require_csrf(request, session_row)
    tenant_id = require_tenant_access(request, _user, db)
    row = get_user(db, id_user)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    row_tenant_ids = {tenant.tenant_id for tenant in list_user_tenants(db, row.id_user)}
    row_tenant_ids.add(row.tenant_id)
    if tenant_id not in row_tenant_ids:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    delete_user(db, row)
    return None

@app.get("/routings", response_model=list[RoutingRead])
def routings(
    request: Request,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current=Depends(require_permission("routings.read")),
):
    user, _session_row = current
    tenant_id = require_tenant_access(request, user, db)
    rows = list_routings(db, limit=limit, offset=offset, tenant_id=tenant_id)
    return [
        RoutingRead(
            routing_id=row.routing_id,
            description_routing=row.description_routing,
            line_id=row.line_id,
            create_date=row.create_date,
        )
        for row in rows
    ]


@app.get("/routings/{routing_id}", response_model=RoutingRead)
def get_routing_endpoint(routing_id: str, request: Request, db: Session = Depends(get_db), current=Depends(require_permission("routings.read"))):
    user, _session_row = current
    tenant_id = require_tenant_access(request, user, db)
    row = get_routing(db, routing_id, tenant_id=tenant_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Routing not found")
    return RoutingRead(
        routing_id=row.routing_id,
        description_routing=row.description_routing,
        line_id=row.line_id,
        create_date=row.create_date,
    )


@app.post("/routings", response_model=RoutingRead, status_code=status.HTTP_201_CREATED)
def create_routing_endpoint(payload: RoutingCreate, request: Request, db: Session = Depends(get_db), current=Depends(require_permission("routings.write"))):
    user, session_row = current
    require_csrf(request, session_row)
    tenant_id = require_tenant_access(request, user, db)
    if not get_line(db, payload.line_id, tenant_id=tenant_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Line not found")
    routing = TbRoutings(
        routing_id=payload.routing_id,
        description_routing=payload.description_routing,
        line_id=payload.line_id,
        tenant_id=tenant_id,
    )
    try:
        row = create_routing(db, routing)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Routing already exists")
    return RoutingRead(
        routing_id=row.routing_id,
        description_routing=row.description_routing,
        line_id=row.line_id,
        create_date=row.create_date,
    )


@app.patch("/routings/{routing_id}", response_model=RoutingRead)
def update_routing_endpoint(routing_id: str, payload: RoutingUpdate, request: Request, db: Session = Depends(get_db), current=Depends(require_permission("routings.write"))):
    user, session_row = current
    require_csrf(request, session_row)
    tenant_id = require_tenant_access(request, user, db)
    row = get_routing(db, routing_id, tenant_id=tenant_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Routing not found")
    updates = payload.model_dump(exclude_unset=True)
    if updates.get("line_id") and not get_line(db, updates["line_id"], tenant_id=tenant_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Line not found")
    for field, value in updates.items():
        setattr(row, field, value)
    try:
        row = update_routing(db, row)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Update conflict")
    return RoutingRead(
        routing_id=row.routing_id,
        description_routing=row.description_routing,
        line_id=row.line_id,
        create_date=row.create_date,
    )


@app.delete("/routings/{routing_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_routing_endpoint(routing_id: str, request: Request, db: Session = Depends(get_db), current=Depends(require_permission("routings.write"))):
    user, session_row = current
    require_csrf(request, session_row)
    tenant_id = require_tenant_access(request, user, db)
    row = get_routing(db, routing_id, tenant_id=tenant_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Routing not found")
    delete_routing(db, row)
    return None


@app.get("/routings/{routing_id}/definition", response_model=RoutingDefinitionRead)
def get_routing_definition_endpoint(routing_id: str, request: Request, db: Session = Depends(get_db), current=Depends(require_permission("routings.read"))):
    user, _session_row = current
    tenant_id = require_tenant_access(request, user, db)
    routing = get_routing(db, routing_id, tenant_id=tenant_id)
    if not routing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Routing not found")
    return RoutingDefinitionRead(
        routing_id=routing.routing_id,
        description_routing=routing.description_routing,
        line_id=routing.line_id,
        create_date=routing.create_date,
        processes=[_serialize_routing_process(row) for row in list_routing_processes(db, routing_id, tenant_id)],
        models=[_serialize_routing_model(row) for row in list_routing_models(db, tenant_id, routing_id)],
    )


@app.post("/routings/{routing_id}/processes", response_model=RoutingProcessRead, status_code=status.HTTP_201_CREATED)
def create_routing_process_endpoint(routing_id: str, payload: RoutingProcessCreate, request: Request, db: Session = Depends(get_db), current=Depends(require_permission("routings.write"))):
    user, session_row = current
    require_csrf(request, session_row)
    tenant_id = require_tenant_access(request, user, db)
    if not get_routing(db, routing_id, tenant_id=tenant_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Routing not found")
    if not get_cell(db, payload.cell_id, tenant_id=tenant_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cell not found")
    row = RoutingProcess(routing_id=routing_id, tenant_id=tenant_id, **payload.model_dump())
    try:
        return _serialize_routing_process(create_routing_process(db, row))
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Process ID or sequence already exists in this routing")


@app.patch("/routings/{routing_id}/processes/{process_id}", response_model=RoutingProcessRead)
def update_routing_process_endpoint(routing_id: str, process_id: str, payload: RoutingProcessUpdate, request: Request, db: Session = Depends(get_db), current=Depends(require_permission("routings.write"))):
    user, session_row = current
    require_csrf(request, session_row)
    tenant_id = require_tenant_access(request, user, db)
    row = get_routing_process(db, routing_id, process_id, tenant_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Routing process not found")
    updates = payload.model_dump(exclude_unset=True)
    if "result_schema" in updates:
        RoutingProcessCreate(
            process_id=row.process_id,
            description=updates.get("description", row.description),
            cell_id=updates.get("cell_id", row.cell_id),
            sequence=updates.get("sequence", row.sequence),
            is_required=updates.get("is_required", row.is_required),
            result_schema=updates["result_schema"],
        )
    if updates.get("cell_id") and not get_cell(db, updates["cell_id"], tenant_id=tenant_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cell not found")
    for field, value in updates.items():
        setattr(row, field, value)
    try:
        return _serialize_routing_process(update_routing_process(db, row))
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Process sequence already exists in this routing")


@app.delete("/routings/{routing_id}/processes/{process_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_routing_process_endpoint(routing_id: str, process_id: str, request: Request, db: Session = Depends(get_db), current=Depends(require_permission("routings.write"))):
    user, session_row = current
    require_csrf(request, session_row)
    tenant_id = require_tenant_access(request, user, db)
    row = get_routing_process(db, routing_id, process_id, tenant_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Routing process not found")
    delete_routing_process(db, row)
    return None


@app.get("/routing-models", response_model=list[RoutingModelRead])
def list_routing_models_endpoint(request: Request, routing_id: str | None = None, db: Session = Depends(get_db), current=Depends(require_permission("routings.read"))):
    user, _session_row = current
    tenant_id = require_tenant_access(request, user, db)
    return [_serialize_routing_model(row) for row in list_routing_models(db, tenant_id, routing_id)]


@app.post("/routing-models", response_model=RoutingModelRead, status_code=status.HTTP_201_CREATED)
def create_routing_model_endpoint(payload: RoutingModelCreate, request: Request, db: Session = Depends(get_db), current=Depends(require_permission("routings.write"))):
    user, session_row = current
    require_csrf(request, session_row)
    tenant_id = require_tenant_access(request, user, db)
    if not get_routing(db, payload.routing_id, tenant_id=tenant_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Routing not found")
    model = get_model(db, payload.model_id, tenant_id=tenant_id)
    if not model:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model not found")
    row = RoutingModel(tenant_id=tenant_id, **payload.model_dump())
    try:
        return _serialize_routing_model(create_routing_model(db, row))
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Model already has a routing")


@app.patch("/routing-models/{model_id}", response_model=RoutingModelRead)
def update_routing_model_endpoint(model_id: str, payload: RoutingModelUpdate, request: Request, db: Session = Depends(get_db), current=Depends(require_permission("routings.write"))):
    user, session_row = current
    require_csrf(request, session_row)
    tenant_id = require_tenant_access(request, user, db)
    row = get_routing_model(db, model_id, tenant_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Routing model not found")
    updates = payload.model_dump(exclude_unset=True)
    if updates.get("routing_id") and not get_routing(db, updates["routing_id"], tenant_id=tenant_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Routing not found")
    for field, value in updates.items():
        setattr(row, field, value)
    return _serialize_routing_model(update_routing_model(db, row))


@app.delete("/routing-models/{model_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_routing_model_endpoint(model_id: str, request: Request, db: Session = Depends(get_db), current=Depends(require_permission("routings.write"))):
    user, session_row = current
    require_csrf(request, session_row)
    tenant_id = require_tenant_access(request, user, db)
    row = get_routing_model(db, model_id, tenant_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Routing model not found")
    delete_routing_model(db, row)
    return None


@app.get("/routing-process-results/{serial_number}", response_model=list[RoutingProcessResultRead])
def list_routing_process_results_endpoint(serial_number: str, request: Request, db: Session = Depends(get_db), current=Depends(require_permission("routings.read"))):
    user, _session_row = current
    tenant_id = require_tenant_access(request, user, db)
    return [_serialize_routing_process_result(row) for row in list_routing_process_results(db, serial_number, tenant_id)]


@app.post("/routing-process-results/ingest", response_model=RoutingProcessResultRead, status_code=status.HTTP_201_CREATED)
def ingest_routing_process_result_endpoint(payload: RoutingProcessResultCreate, request: Request, db: Session = Depends(get_db)):
    client = require_production_ingest_api_key(request, db, payload)
    tenant_id = client.tenant_id if client is not None else get_default_tenant_id()
    model = get_routing_model(db, payload.model_id, tenant_id)
    if not model or not model.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Active routing model not found")
    process = get_routing_process(db, model.routing_id, payload.process_id, tenant_id)
    if not process:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Process is not defined for the reference routing")
    _validate_result_values(process, payload.result, payload.result_values)
    row = RoutingProcessResult(
        tenant_id=tenant_id,
        routing_id=model.routing_id,
        model_id=payload.model_id,
        serial_number=payload.serial_number,
        process_id=payload.process_id,
        cell_id=process.cell_id,
        result=payload.result,
        result_values=payload.result_values,
        result_schema=process.result_schema or [],
        process_datetime=payload.process_datetime,
        source_system=payload.source_system,
    )
    measurements = _build_traceability_measurements(process, payload, model.routing_id, process.cell_id, tenant_id)
    return _serialize_routing_process_result(create_routing_process_result(db, row, measurements))
