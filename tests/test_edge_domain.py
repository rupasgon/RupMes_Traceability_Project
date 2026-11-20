import asyncio
from datetime import date, datetime, timedelta, timezone

from rupmes_edge.store import EdgeStore

from rupmes_edge.domain import LiveStation, StationDefinition, StationState, utc_now
from rupmes_edge.config import EdgeConfig
from rupmes_edge.runtime import EdgeRuntime
from rupmes_edge.stoppages import StoppagePolicy


def station() -> LiveStation:
    return LiveStation(StationDefinition("ST01", "Test station", 20.0, {}))


def test_fault_has_priority_over_running():
    live = station()
    now = utc_now()
    live.apply("Running", True, now)
    live.apply("FaultActive", True, now)

    assert live.state(True, now) == StationState.FAULT


def test_stale_data_is_disconnected():
    live = station()
    now = utc_now()
    live.apply("Running", True, now - timedelta(seconds=6))

    assert live.state(True, now) == StationState.DISCONNECTED


def test_cycle_complete_records_plc_cycle_time_once_per_pulse():
    live = station()
    now = utc_now()
    live.apply("CycleTime", 21.5, now)
    live.apply("CycleComplete", True, now)
    live.apply("CycleComplete", True, now)

    assert live.completed_cycles == 1
    assert live.last_cycle_seconds == 21.5
    assert live.cycles_over_target == 1


def test_snapshot_uses_the_configured_output_station_for_line_parts():
    runtime = EdgeRuntime(
        "Demo line",
        [
            StationDefinition("ST01", "Assembly", 20.0, {}, is_output_station=False),
            StationDefinition("ST02", "Packing", 20.0, {}, is_output_station=True),
        ],
    )
    now = utc_now()
    runtime.set_endpoint_health("default", True)
    asyncio.run(runtime.apply_update("ST01", "PartsCounter", 12, now))
    asyncio.run(runtime.apply_update("ST02", "PartsCounter", 9, now))

    snapshot = runtime.snapshot()

    assert snapshot["line_parts"] == 9
    assert snapshot["line_parts_station"] == "Packing"


def test_bmw_catalog_metadata_is_applied_without_changing_node_ids():
    config = EdgeConfig.model_validate(
        {
            "line_id": "BMW",
            "line_name": "BMW assembly line",
            "demo_mode": True,
            "endpoints": [{"endpoint_id": "plc", "url": "opc.tcp://localhost:4840"}],
            "stations": [
                {
                    "station_id": "ST01",
                    "name": "PLC station 1",
                    "endpoint_id": "plc",
                    "target_cycle_seconds": 20,
                    "node_map": {"Running": "ns=4;s=OPC_UA.ST01.Running"},
                }
            ],
        }
    )

    station = config.station_definitions()[0]

    assert station.process_id == "P200"
    assert station.description == "Load and assembly DI button into the DI knob"
    assert station.node_map["Running"] == "ns=4;s=OPC_UA.ST01.Running"


def test_timeline_keeps_a_stop_that_started_before_the_production_day(tmp_path):
    store = EdgeStore(tmp_path / "edge.sqlite")
    store.record_state("ST01", "IDLE", datetime(2026, 11, 3, 4, 0, tzinfo=timezone.utc))
    store.record_state("ST01", "RUNNING", datetime(2026, 11, 3, 7, 0, tzinfo=timezone.utc))

    timeline = store.stoppage_timeline(["ST01"], date(2026, 11, 3), 1, "Europe/Madrid")

    assert len(timeline["events"]) == 1
    assert timeline["events"][0]["type"] == "stop_auto"
    # The production day begins at 06:00 local time (05:00 UTC in November).
    assert timeline["events"][0]["duration_seconds"] == 7200
    store.close()


def test_stoppage_is_opened_once_after_debounce_and_closed_without_future_projection(tmp_path):
    store = EdgeStore(tmp_path / "edge.sqlite")
    runtime = EdgeRuntime(
        "BMW", [StationDefinition("ST01", "Test", 20, {})], store,
        line_id="BMW", stoppage_policy=StoppagePolicy(open_after_seconds=2, close_after_seconds=1),
    )
    start = datetime(2026, 11, 17, 8, 0, tzinfo=timezone.utc)
    runtime.set_endpoint_health("default", True)
    asyncio.run(runtime.apply_update("ST01", "Running", False, start))
    runtime.tick(start + timedelta(seconds=2))
    open_events = store.load_open_stoppages()
    assert len(open_events) == 1
    assert open_events[0]["reason"] == "WAITING"

    asyncio.run(runtime.apply_update("ST01", "Running", True, start + timedelta(seconds=3)))
    runtime.tick(start + timedelta(seconds=4))
    assert store.load_open_stoppages() == []
    events = store.stoppages(["ST01"], start, start + timedelta(seconds=10), start + timedelta(seconds=4))
    assert events[0]["duration_seconds"] == 3.0
    store.close()


def test_open_stoppage_is_recovered_after_runtime_restart(tmp_path):
    store = EdgeStore(tmp_path / "edge.sqlite")
    started = datetime(2026, 11, 17, 8, 0, tzinfo=timezone.utc)
    event = store.open_stoppage(
        line_id="BMW", station_id="ST01", reason="MANUAL", source_state="MANUAL",
        started_at=started, shift="TM", classification="AUTOMATIC", confidence=0.95,
        alarm_ids=[], alarm_code=None,
    )
    runtime = EdgeRuntime(
        "BMW", [StationDefinition("ST01", "Test", 20, {})], store,
        line_id="BMW", stoppage_policy=StoppagePolicy(open_after_seconds=0, close_after_seconds=1),
    )
    assert runtime._stoppage_trackers["ST01"].open_event["id"] == event["id"]
    store.close()
