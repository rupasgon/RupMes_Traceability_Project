from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator

from rupmes_edge.bmw_station_catalog import get_bmw_station_metadata
from rupmes_edge.domain import StationDefinition
from rupmes_edge.stoppages import StoppagePolicy


SIMULATOR_ENDPOINT = "opc.tcp://127.0.0.1:4840/rupmes/simulator/"
CONFIG_VERSION = 1


class SecurityConfig(BaseModel):
    policy: Literal["None", "Basic256Sha256", "Aes128Sha256RsaOaep", "Aes256Sha256RsaPss"] = "None"
    mode: Literal["None", "Sign", "SignAndEncrypt"] = "None"
    client_certificate_path: str | None = None
    private_key_path: str | None = None
    server_certificate_path: str | None = None

    @model_validator(mode="after")
    def validate_security(self) -> "SecurityConfig":
        secure = self.policy != "None" or self.mode != "None"
        if secure and (self.policy == "None" or self.mode == "None"):
            raise ValueError("A secure OPC UA endpoint requires both a policy and a mode")
        if secure and not all((self.client_certificate_path, self.private_key_path, self.server_certificate_path)):
            raise ValueError("Secure OPC UA endpoints require client certificate, private key, and trusted server certificate")
        return self


class OpcUaEndpointConfig(BaseModel):
    endpoint_id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    url: str
    application_uri: str | None = None
    subscription_interval_ms: int = Field(default=500, ge=100, le=60_000)
    username: str | None = None
    password_secret_ref: str | None = None
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    connect_timeout_seconds: int = Field(default=15, ge=1, le=120)

    @field_validator("url")
    @classmethod
    def validate_opcua_url(cls, value: str) -> str:
        if not value.startswith("opc.tcp://"):
            raise ValueError("OPC UA endpoints must use opc.tcp://")
        return value

    @field_validator("application_uri")
    @classmethod
    def validate_application_uri(cls, value: str | None) -> str | None:
        if value is not None and not value.startswith("urn:"):
            raise ValueError("OPC UA application URI must start with urn:")
        return value

    @model_validator(mode="after")
    def validate_credentials(self) -> "OpcUaEndpointConfig":
        if self.username and not self.password_secret_ref:
            raise ValueError("username requires password_secret_ref")
        if self.password_secret_ref and not self.username:
            raise ValueError("password_secret_ref requires username")
        return self


class StationConfig(BaseModel):
    station_id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=100)
    endpoint_id: str
    target_cycle_seconds: float = Field(gt=0, le=3600)
    stale_after_seconds: float = Field(default=5, ge=1, le=3600)
    is_output_station: bool = False
    node_map: dict[str, str] = Field(min_length=1)
    process_id: str | None = Field(default=None, max_length=20)
    description: str | None = Field(default=None, max_length=200)
    physical_order: int | None = Field(default=None, ge=1)

    @field_validator("node_map")
    @classmethod
    def validate_node_map(cls, value: dict[str, str]) -> dict[str, str]:
        allowed = {"Running", "CycleActive", "CycleComplete", "CycleTime", "PartsCounter", "FaultActive", "AutoMode", "AlarmCode", "Heartbeat"}
        unknown = set(value) - allowed
        if unknown:
            raise ValueError(f"Unsupported station metric(s): {', '.join(sorted(unknown))}")
        if any(not node_id.strip() for node_id in value.values()):
            raise ValueError("NodeIds cannot be blank")
        return value


class ProductionCounterConfig(BaseModel):
    """A named, read-only production counter published by an OPC UA endpoint."""

    counter_id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=100)
    endpoint_id: str
    quantity_node: str = Field(min_length=1)
    ok_node: str | None = None
    nok_node: str | None = None


class LineCycleConfig(BaseModel):
    """Optional full-piece cycle, independent from the individual stations."""

    endpoint_id: str
    cycle_time_node: str = Field(min_length=1)
    cycle_complete_node: str = Field(min_length=1)
    target_cycle_seconds: float = Field(gt=0, le=3600)


class StorageConfig(BaseModel):
    database_path: str = "data/rupmes-edge.db"
    retention_days: int = Field(default=30, ge=1, le=3650)


class StoppagePolicyConfig(BaseModel):
    open_after_seconds: float = Field(default=5, ge=0, le=3600)
    close_after_seconds: float = Field(default=3, ge=0, le=3600)
    micro_stop_seconds: float = Field(default=60, gt=0, le=3600)

    def to_domain(self) -> StoppagePolicy:
        return StoppagePolicy(**self.model_dump())


class CentralSyncConfig(BaseModel):
    """Optional outbound-only delivery of durable downtime events."""

    enabled: bool = False
    base_url: str | None = None
    host_header: str | None = None
    client_id: str | None = None
    api_key_secret_ref: str | None = None
    interval_seconds: int = Field(default=30, ge=5, le=3600)

    @model_validator(mode="after")
    def validate_delivery(self) -> "CentralSyncConfig":
        if self.enabled and not all((self.base_url, self.host_header, self.client_id, self.api_key_secret_ref)):
            raise ValueError("Enabled central sync requires base_url, host_header, client_id, and api_key_secret_ref")
        if self.base_url and not self.base_url.startswith(("http://", "https://")):
            raise ValueError("central sync base_url must be HTTP(S)")
        return self


class AdminConfig(BaseModel):
    bind_host: str = "127.0.0.1"
    port: int = Field(default=8020, ge=1024, le=65535)
    token_secret_ref: str | None = None


class EdgeConfig(BaseModel):
    config_version: Literal[CONFIG_VERSION] = CONFIG_VERSION
    line_id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    line_name: str = Field(min_length=1, max_length=100)
    timezone: str = "Europe/Madrid"
    demo_mode: bool = False
    storage: StorageConfig = Field(default_factory=StorageConfig)
    stoppage_policy: StoppagePolicyConfig = Field(default_factory=StoppagePolicyConfig)
    central_sync: CentralSyncConfig = Field(default_factory=CentralSyncConfig)
    admin: AdminConfig = Field(default_factory=AdminConfig)
    endpoints: list[OpcUaEndpointConfig] = Field(min_length=1)
    stations: list[StationConfig] = Field(min_length=1)
    production_counters: list[ProductionCounterConfig] = Field(default_factory=list)
    line_cycle: LineCycleConfig | None = None

    @model_validator(mode="after")
    def validate_references(self) -> "EdgeConfig":
        endpoint_ids = [endpoint.endpoint_id for endpoint in self.endpoints]
        if len(endpoint_ids) != len(set(endpoint_ids)):
            raise ValueError("Endpoint IDs must be unique")
        station_ids = [station.station_id for station in self.stations]
        if len(station_ids) != len(set(station_ids)):
            raise ValueError("Station IDs must be unique")
        missing = {station.endpoint_id for station in self.stations} - set(endpoint_ids)
        if missing:
            raise ValueError(f"Stations reference undefined endpoint(s): {', '.join(sorted(missing))}")
        missing_counter_endpoints = {counter.endpoint_id for counter in self.production_counters} - set(endpoint_ids)
        if missing_counter_endpoints:
            raise ValueError(f"Production counters reference undefined endpoint(s): {', '.join(sorted(missing_counter_endpoints))}")
        if self.line_cycle and self.line_cycle.endpoint_id not in endpoint_ids:
            raise ValueError("Line cycle references an undefined endpoint")
        if not self.demo_mode:
            insecure = [endpoint.endpoint_id for endpoint in self.endpoints if endpoint.security.policy == "None"]
            if insecure:
                raise ValueError(f"Production configuration requires secure OPC UA endpoints; insecure: {', '.join(insecure)}")
        return self

    def station_definitions(self) -> list[StationDefinition]:
        definitions = []
        for item in self.stations:
            metadata = get_bmw_station_metadata(item.station_id)
            definitions.append(StationDefinition(
                station_id=item.station_id,
                name=item.name,
                target_cycle_seconds=item.target_cycle_seconds,
                node_map=item.node_map,
                endpoint_id=item.endpoint_id,
                is_output_station=item.is_output_station,
                process_id=item.process_id or (metadata.process_id if metadata else None),
                description=item.description or (metadata.description if metadata else item.name),
                physical_order=item.physical_order or (metadata.order if metadata else None),
                opcua_pending=bool(metadata and metadata.opcua_pending),
            ))
        return definitions

    def effective_production_counters(self) -> list[ProductionCounterConfig]:
        """Use explicit configuration; retain the existing BMW interface as a safe default."""
        if self.production_counters:
            return self.production_counters
        endpoint_id = next((station.endpoint_id for station in self.stations if station.node_map.get("CycleTime", "").startswith("ns=4;s=OPC_UA.ST")), None)
        if not endpoint_id:
            return []
        prefix = "ns=4;s=OPC_UA"
        return [
            ProductionCounterConfig(counter_id="total", name="Total production", endpoint_id=endpoint_id, quantity_node=f"{prefix}.Contador_Total.QTY", ok_node=f"{prefix}.Contador_Total.QTY_OK", nok_node=f"{prefix}.Contador_Total.QTY_NOK"),
            ProductionCounterConfig(counter_id="wi", name="WI production", endpoint_id=endpoint_id, quantity_node=f"{prefix}.Contador_WI.QTY", ok_node=f"{prefix}.Contador_WI.QTY_OK", nok_node=f"{prefix}.Contador_WI.QTY_NOK"),
            ProductionCounterConfig(counter_id="di", name="DI production", endpoint_id=endpoint_id, quantity_node=f"{prefix}.Contador_DI.QTY", ok_node=f"{prefix}.Contador_DI.QTY_OK", nok_node=f"{prefix}.Contador_DI.QTY_NOK"),
        ]

    def sanitized(self) -> dict:
        result = self.model_dump()
        for endpoint in result["endpoints"]:
            endpoint["password_configured"] = bool(endpoint["password_secret_ref"] and os.getenv(endpoint["password_secret_ref"]))
        result["admin"]["token_configured"] = bool(result["admin"]["token_secret_ref"] and os.getenv(result["admin"]["token_secret_ref"]))
        return result


def secret_from_reference(reference: str | None) -> SecretStr | None:
    if not reference:
        return None
    value = os.getenv(reference)
    if not value:
        raise RuntimeError(f"Required secret environment variable is not set: {reference}")
    return SecretStr(value)


def load_config(path: str | Path) -> EdgeConfig:
    return EdgeConfig.model_validate_json(Path(path).read_text(encoding="utf-8"))


def default_config_path() -> Path:
    configured = os.getenv("RUPMES_EDGE_CONFIG")
    if configured:
        return Path(configured)
    root = (Path(os.getenv("PROGRAMDATA", str(Path.home()))) / "RupMES Edge") if os.name == "nt" else Path("/etc/rupmes-edge")
    return root / "config.json"


def demo_config() -> EdgeConfig:
    stations = []
    for station_id, name, target in (("ST01", "Load station", 18.0), ("ST02", "Assembly station", 24.0), ("ST03", "Inspection station", 20.0), ("ST04", "Unload station", 16.0)):
        prefix = f"ns=2;s=Stations.{station_id}"
        stations.append({"station_id": station_id, "name": name, "endpoint_id": "simulator", "target_cycle_seconds": target, "is_output_station": station_id == "ST04", "node_map": {metric: f"{prefix}.{metric}" for metric in ("Running", "CycleActive", "CycleComplete", "CycleTime", "PartsCounter", "FaultActive", "AutoMode", "AlarmCode", "Heartbeat")}})
    return EdgeConfig.model_validate({"line_id": "DEMO", "line_name": "BMW Demo Line", "demo_mode": True, "endpoints": [{"endpoint_id": "simulator", "url": SIMULATOR_ENDPOINT}], "stations": stations})


def config_to_json(config: EdgeConfig) -> str:
    return json.dumps(config.model_dump(), indent=2) + "\n"
