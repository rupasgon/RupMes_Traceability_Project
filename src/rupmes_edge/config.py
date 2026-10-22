from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator

from rupmes_edge.domain import StationDefinition


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


class ProductionCounterConfig(BaseModel):
    """One production counter rendered in the dashboard header."""

    counter_id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=100)
    quantity_node: str | None = None
    ok_node: str | None = None
    nok_node: str | None = None

    @model_validator(mode="after")
    def validate_nodes(self) -> "ProductionCounterConfig":
        if not any((self.quantity_node, self.ok_node, self.nok_node)):
            raise ValueError("A production counter requires at least one NodeId")
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
    production_counters: list[ProductionCounterConfig] = Field(default_factory=list)

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
        counter_ids = [counter.counter_id for counter in self.production_counters]
        if len(counter_ids) != len(set(counter_ids)):
            raise ValueError("Production counter IDs must be unique per endpoint")
        return self


class StationConfig(BaseModel):
    station_id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=100)
    endpoint_id: str
    target_cycle_seconds: float = Field(gt=0, le=3600)
    stale_after_seconds: float = Field(default=5, ge=1, le=3600)
    is_output_station: bool = False
    node_map: dict[str, str] = Field(min_length=1)

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


class LineCycleConfig(BaseModel):
    """Optional line-level cycle, independent from the station cycle signals."""

    endpoint_id: str
    cycle_time_node: str = Field(min_length=1)
    cycle_complete_node: str = Field(min_length=1)
    target_cycle_seconds: float = Field(gt=0, le=3600)

    @field_validator("cycle_time_node", "cycle_complete_node")
    @classmethod
    def validate_node_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Line-cycle NodeIds cannot be blank")
        return value.strip()


class StorageConfig(BaseModel):
    database_path: str = "data/rupmes-edge.db"
    retention_days: int = Field(default=30, ge=1, le=3650)


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
    admin: AdminConfig = Field(default_factory=AdminConfig)
    endpoints: list[OpcUaEndpointConfig] = Field(min_length=1)
    stations: list[StationConfig] = Field(min_length=1)
    line_cycle: LineCycleConfig | None = None
    line_node_map: dict[str, str] = Field(default_factory=dict)

    @field_validator("line_node_map")
    @classmethod
    def validate_line_node_map(cls, value: dict[str, str]) -> dict[str, str]:
        allowed = {"Total", "TotalOK", "TotalNOK", "WI", "WIOK", "WINOK", "DI", "DIOK", "DINOK", "Heartbeat"}
        unknown = set(value) - allowed
        if unknown:
            raise ValueError(f"Unsupported line metric(s): {', '.join(sorted(unknown))}")
        if any(not node_id.strip() for node_id in value.values()):
            raise ValueError("Line NodeIds cannot be blank")
        return value
    # Optional production counters.  The standard BMW interface is detected
    # automatically when this is omitted, keeping old configurations valid.
    line_node_map: dict[str, str] = Field(default_factory=dict)

    @field_validator("line_node_map")
    @classmethod
    def validate_line_node_map(cls, value: dict[str, str]) -> dict[str, str]:
        allowed = {"Total", "TotalOK", "TotalNOK", "WI", "WIOK", "WINOK", "DI", "DIOK", "DINOK", "Heartbeat"}
        unknown = set(value) - allowed
        if unknown:
            raise ValueError(f"Unsupported line metric(s): {', '.join(sorted(unknown))}")
        if any(not node_id.strip() for node_id in value.values()):
            raise ValueError("Line NodeIds cannot be blank")
        return value

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
        if self.line_cycle and self.line_cycle.endpoint_id not in endpoint_ids:
            raise ValueError("Line cycle references an undefined endpoint")
        if not self.demo_mode:
            insecure = [endpoint.endpoint_id for endpoint in self.endpoints if endpoint.security.policy == "None"]
            if insecure:
                raise ValueError(f"Production configuration requires secure OPC UA endpoints; insecure: {', '.join(insecure)}")
        return self

    def station_definitions(self) -> list[StationDefinition]:
        return [StationDefinition(station_id=item.station_id, name=item.name, target_cycle_seconds=item.target_cycle_seconds, node_map=item.node_map, endpoint_id=item.endpoint_id, is_output_station=item.is_output_station) for item in self.stations]

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
