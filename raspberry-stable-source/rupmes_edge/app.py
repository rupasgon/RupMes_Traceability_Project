from __future__ import annotations

import asyncio
import secrets
import threading
from time import monotonic
from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse

from rupmes_edge.config import EdgeConfig, secret_from_reference
from rupmes_edge.opcua import MetricPollCollector, OpcUaSubscriptionCollector
from rupmes_edge.runtime import EdgeRuntime
from rupmes_edge.process_metrics import enable_process_metrics
from rupmes_edge.store import EdgeStore
from rupmes_edge.sync import CentralStoppageSync


def create_app(bootstrap_config: EdgeConfig, config_path: str | Path | None = None) -> FastAPI:
    store = EdgeStore(bootstrap_config.storage.database_path)
    stored_configuration = store.load_configuration()
    config = EdgeConfig.model_validate_json(stored_configuration) if stored_configuration else bootstrap_config
    if stored_configuration is None:
        store.save_configuration(config.model_dump_json())
    stations = config.station_definitions()
    for station in stations:
        total_node = station.node_map.get("CycleTime", "")
        if total_node.endswith(".CycleTime_Estacion"):
            station.node_map["CycleTime"] = total_node.replace(
                ".CycleTime_Estacion", ".CycleTime_Total"
            )
            station.node_map["ProcessCycleTime"] = total_node
        elif total_node.endswith(".CycleTime_Total"):
            station.node_map["ProcessCycleTime"] = total_node.replace(
                ".CycleTime_Total", ".CycleTime_Estacion"
            )
    counters = config.effective_production_counters()
    runtime = EdgeRuntime(config.line_name, stations, store, counters, config.line_cycle, line_id=config.line_id, timezone_name=config.timezone, stoppage_policy=config.stoppage_policy.to_domain())
    enable_process_metrics(runtime)
    # Several wallboards can be open at once.  Serve a shared, sub-second
    # snapshot instead of taking the runtime lock and serialising identical
    # data for every browser request.
    snapshot_cache: tuple[float, dict] | None = None
    snapshot_cache_lock = threading.Lock()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        collectors, tasks = [], []
        async def state_tick_loop():
            while True:
                runtime.tick()
                await asyncio.sleep(1)
        tasks.append(asyncio.create_task(state_tick_loop()))
        if config.central_sync.enabled:
            api_key = secret_from_reference(config.central_sync.api_key_secret_ref)
            sync = CentralStoppageSync(store, config.central_sync, api_key.get_secret_value())
            async def central_sync_loop():
                while True:
                    await asyncio.to_thread(sync.run_once)
                    await asyncio.sleep(config.central_sync.interval_seconds)
            tasks.append(asyncio.create_task(central_sync_loop()))
        for endpoint in config.endpoints:
            assigned = [station for station in stations if station.endpoint_id == endpoint.endpoint_id]
            collector = OpcUaSubscriptionCollector(endpoint, assigned, runtime.apply_update, lambda connected, error, endpoint_id=endpoint.endpoint_id: runtime.set_endpoint_health(endpoint_id, connected, error), endpoint.subscription_interval_ms)
            collectors.append(collector)
            tasks.append(asyncio.create_task(collector.run()))
        for counter in counters:
            endpoint = next(item for item in config.endpoints if item.endpoint_id == counter.endpoint_id)
            nodes = {"quantity": counter.quantity_node}
            if counter.ok_node:
                nodes["ok"] = counter.ok_node
            if counter.nok_node:
                nodes["nok"] = counter.nok_node
            async def on_counter(metric, value, observed_at, counter_id=counter.counter_id):
                await runtime.apply_counter_update(counter_id, metric, value, observed_at)
            collector = MetricPollCollector(endpoint, nodes, on_counter, lambda connected, error, endpoint_id=endpoint.endpoint_id: runtime.set_endpoint_health(endpoint_id, connected, error), endpoint.subscription_interval_ms)
            collectors.append(collector)
            tasks.append(asyncio.create_task(collector.run()))
        if config.line_cycle:
            endpoint = next(item for item in config.endpoints if item.endpoint_id == config.line_cycle.endpoint_id)
            async def on_line_cycle(metric, value, observed_at):
                await runtime.apply_line_cycle_update(metric, value, observed_at)
            collector = MetricPollCollector(endpoint, {"CycleTime": config.line_cycle.cycle_time_node, "CycleComplete": config.line_cycle.cycle_complete_node}, on_line_cycle, lambda connected, error, endpoint_id=endpoint.endpoint_id: runtime.set_endpoint_health(endpoint_id, connected, error), endpoint.subscription_interval_ms)
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
        nonlocal snapshot_cache
        now = monotonic()
        with snapshot_cache_lock:
            if snapshot_cache and now - snapshot_cache[0] < 1.0:
                return snapshot_cache[1]
            payload = runtime.snapshot()
            snapshot_cache = (now, payload)
            return payload

    @app.get("/edge/api/stations/{station_id}/daily")
    def station_daily_history(station_id: str, selected_date: date | None = None) -> dict:
        if station_id not in runtime.stations:
            raise HTTPException(status_code=404, detail="Unknown station")
        day = selected_date or datetime.now(ZoneInfo(config.timezone)).date()
        return store.daily_history(station_id, day, config.timezone)

    @app.get("/edge/api/timeline")
    def stoppage_timeline(selected_date: date | None = None, days: int = 7, station_id: str | None = None) -> dict:
        if station_id and station_id not in runtime.stations:
            raise HTTPException(status_code=404, detail="Unknown station")
        selected_ids = [station_id] if station_id else list(runtime.stations)
        last_day = selected_date or datetime.now(ZoneInfo(config.timezone)).date()
        result = store.stoppage_timeline(selected_ids, last_day, days, config.timezone)
        result["stations"] = [
            {"id": station.station_id, "name": station.name, "process_id": station.process_id, "description": station.description, "physical_order": station.physical_order}
            for station in stations if station.station_id in selected_ids
        ]
        return result

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

    @app.get("/edge/api/admin/process-targets")
    def get_process_targets() -> dict[str, float]:
        return runtime.get_process_targets()

    @app.put("/edge/api/admin/process-targets")
    def update_process_targets(targets: dict[str, float]) -> dict[str, float]:
        return runtime.set_process_targets(targets)

    return app
