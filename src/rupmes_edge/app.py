from __future__ import annotations

import asyncio
import secrets
from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse

from rupmes_edge.config import EdgeConfig, secret_from_reference
from rupmes_edge.opcua import LineCycleCollector, OpcUaSubscriptionCollector
from rupmes_edge.runtime import EdgeRuntime
from rupmes_edge.store import EdgeStore


def create_app(bootstrap_config: EdgeConfig, config_path: str | Path | None = None) -> FastAPI:
    store = EdgeStore(bootstrap_config.storage.database_path)
    stored_configuration = store.load_configuration()
    config = EdgeConfig.model_validate_json(stored_configuration) if stored_configuration else bootstrap_config
    if stored_configuration is None:
        store.save_configuration(config.model_dump_json())
    stations = config.station_definitions()
    runtime = EdgeRuntime(config.line_name, stations, store, config.line_cycle)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        collectors, tasks = [], []
        for endpoint in config.endpoints:
            assigned = [station for station in stations if station.endpoint_id == endpoint.endpoint_id]
            collector = OpcUaSubscriptionCollector(endpoint, assigned, runtime.apply_update, lambda connected, error, endpoint_id=endpoint.endpoint_id: runtime.set_endpoint_health(endpoint_id, connected, error), endpoint.subscription_interval_ms)
            collectors.append(collector)
            tasks.append(asyncio.create_task(collector.run()))
        if config.line_cycle:
            endpoint = next(item for item in config.endpoints if item.endpoint_id == config.line_cycle.endpoint_id)
            collector = LineCycleCollector(
                endpoint,
                config.line_cycle,
                runtime.apply_line_cycle_update,
                lambda connected, error, endpoint_id=endpoint.endpoint_id: runtime.set_endpoint_health(endpoint_id, connected, error),
                endpoint.subscription_interval_ms,
            )
            collectors.append(collector)
            tasks.append(asyncio.create_task(collector.run()))
        try:
            yield
        finally:
            for collector in collectors:
                collector.stop()
            await asyncio.gather(*tasks, return_exceptions=True)
            store.close()

    app = FastAPI(title="RupMES Edge Dashboard", lifespan=lifespan)
    static_dir = Path(__file__).with_name("static")

    def require_admin(token: str | None) -> None:
        try:
            expected = secret_from_reference(config.admin.token_secret_ref)
        except RuntimeError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        if expected and not (token and secrets.compare_digest(token, expected.get_secret_value())):
            raise HTTPException(status_code=401, detail="Invalid edge administrator token")

    @app.get("/edge")
    def dashboard() -> FileResponse:
        return FileResponse(static_dir / "index.html")

    @app.get("/edge/api/snapshot")
    def snapshot() -> dict:
        return runtime.snapshot()

    @app.get("/edge/api/stations/{station_id}/daily")
    def station_daily_history(station_id: str, selected_date: date | None = None) -> dict:
        if station_id not in runtime.stations:
            raise HTTPException(status_code=404, detail="Unknown station")
        day = selected_date or datetime.now(ZoneInfo(config.timezone)).date()
        return store.daily_history(station_id, day, config.timezone)

    @app.get("/edge/health")
    def health() -> dict:
        result = runtime.snapshot()["connection"]
        return {"status": "ok" if result["connected"] else "degraded", **result}

    @app.get("/edge/api/admin/config")
    def get_config(x_edge_admin_token: str | None = Header(default=None)) -> dict:
        require_admin(x_edge_admin_token)
        return config.sanitized()

    @app.put("/edge/api/admin/config")
    def save_config(updated_config: EdgeConfig, x_edge_admin_token: str | None = Header(default=None)) -> dict:
        nonlocal config
        require_admin(x_edge_admin_token)
        store.save_configuration(updated_config.model_dump_json())
        # Keep the configuration endpoint consistent during this process.  The
        # OPC collectors deliberately continue with the previous runtime until
        # the service is restarted, but a subsequent "Load configuration" must
        # show the values that were just persisted.
        config = updated_config
        return {
            "saved": True,
            "restart_required": True,
            "message": "Configuration saved. Restart the RupMES Edge Dashboard task to apply it.",
        }

    return app
