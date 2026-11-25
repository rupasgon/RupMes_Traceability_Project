from __future__ import annotations

from datetime import datetime
from threading import RLock
from typing import Any

from rupmes_edge.domain import LiveStation, StationDefinition, utc_now
from rupmes_edge.stoppages import StoppagePolicy, StoppageTracker


class EdgeRuntime:
    """Thread-safe in-memory runtime state shared by all dashboard viewers."""

    def __init__(self, line_name: str, stations: list[StationDefinition], store=None, production_counters=None, line_cycle_config=None, *, line_id=None, timezone_name="Europe/Madrid", stoppage_policy=None):
        self.line_name = line_name
        self.line_id = line_id or line_name
        self.stations = {definition.station_id: LiveStation(definition) for definition in stations}
        self.endpoint_health: dict[str, tuple[bool, str | None]] = {}
        self._endpoint_was_connected: dict[str, bool] = {}
        self.store = store
        self._last_states: dict[str, str] = {}
        self._state_since: dict[str, datetime] = {}
        self._lock = RLock()
        self.line_cycle_config = line_cycle_config
        self._line_cycle_signals: dict[str, Any] = {}
        self._line_cycle_last_complete = False
        self._line_cycle_last_seconds: float | None = None
        self._line_cycle_completed = 0
        self._line_cycle_over_target = 0
        self._line_cycle_total_seconds = 0.0
        self.line_counters = {item.counter_id: {"id": item.counter_id, "name": item.name, "quantity": None, "ok": None, "nok": None} for item in (production_counters or [])}
        policy = stoppage_policy or StoppagePolicy()
        self._stoppages = {item.station_id: StoppageTracker(item.station_id, store, line_id or line_name, timezone_name, policy) for item in stations} if store else {}
        if store:
            for event in store.load_open_stoppages():
                if event["station_id"] in self._stoppages:
                    self._stoppages[event["station_id"]].restore(event)

    async def apply_update(self, station_id: str, metric: str, value: Any, observed_at: datetime) -> None:
        with self._lock:
            station = self.stations[station_id]
            previous_cycles = station.completed_cycles
            station.apply(metric, value, observed_at)
            if self.store and station.completed_cycles > previous_cycles and station.last_cycle_seconds is not None:
                self.store.record_cycle(station_id, station.last_cycle_seconds, observed_at)
            if self.store and metric == "PartsCounter":
                try:
                    self.store.record_counter(station_id, float(value), observed_at)
                except (TypeError, ValueError):
                    pass
            self.capture_states(observed_at)

    async def apply_counter_update(self, counter_id: str, metric: str, value: Any, observed_at: datetime) -> None:
        with self._lock:
            if counter_id in self.line_counters:
                self.line_counters[counter_id][metric] = value
                # MetricPollCollector reads quantity, OK, then NOK.  At NOK
                # the three values form one coherent PLC snapshot.
                if self.store and metric == "nok":
                    counter = self.line_counters[counter_id]
                    self.store.record_production_counter(self.line_id, counter_id, counter["name"], counter["quantity"], counter["ok"], counter["nok"], observed_at)

    async def apply_line_cycle_update(self, metric: str, value: Any, observed_at: datetime) -> None:
        with self._lock:
            self._line_cycle_signals[metric] = value
            if metric != "CycleComplete":
                return
            is_complete = bool(value)
            if is_complete and not self._line_cycle_last_complete:
                try:
                    seconds = float(self._line_cycle_signals.get("CycleTime"))
                except (TypeError, ValueError):
                    seconds = None
                if seconds is not None:
                    self._line_cycle_last_seconds = seconds
                    self._line_cycle_completed += 1
                    self._line_cycle_total_seconds += seconds
                    if self.line_cycle_config and seconds > self.line_cycle_config.target_cycle_seconds:
                        self._line_cycle_over_target += 1
            self._line_cycle_last_complete = is_complete

    def set_endpoint_health(self, endpoint_id: str, connected: bool, error: str | None = None) -> None:
        with self._lock:
            self.endpoint_health[endpoint_id] = (connected, error)
            if connected:
                self._endpoint_was_connected[endpoint_id] = True
            if self.store:
                self.store.record_connector(endpoint_id, connected, error, utc_now())
            self.capture_states(utc_now())

    def capture_states(self, observed_at: datetime) -> None:
        for station_id, station in self.stations.items():
            connected = self.endpoint_health.get(station.definition.endpoint_id, (False, None))[0]
            item = station.as_dict(connected, observed_at)
            state = item["state"]
            if self.store and self._last_states.get(station_id) != state:
                self.store.record_state(station_id, state, observed_at)
            # Do not classify the process boot sequence as a communications
            # outage.  A loss is meaningful only after this endpoint has
            # successfully connected at least once in the current process.
            if station_id in self._stoppages and not (
                state == "DISCONNECTED" and not self._endpoint_was_connected.get(station.definition.endpoint_id, False)
            ):
                self._stoppages[station_id].observe(state, item, observed_at)
            if self._last_states.get(station_id) != state:
                self._state_since[station_id] = observed_at
            self._last_states[station_id] = state

    def tick(self, observed_at: datetime | None = None) -> None:
        with self._lock:
            self.capture_states(observed_at or utc_now())

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            now = utc_now()
            stations = []
            for station in self.stations.values():
                item = station.as_dict(self.endpoint_health.get(station.definition.endpoint_id, (False, None))[0], now)
                state_since = self._state_since.get(station.definition.station_id)
                item["state_since"] = state_since.isoformat() if state_since else item["last_update"]
                stations.append(item)
            health = {endpoint_id: {"connected": value[0], "error": value[1]} for endpoint_id, value in self.endpoint_health.items()}
            output_counters = [item for item in stations if item["is_output_station"] and item["parts_counter"] is not None]
            candidates = [item for item in stations if item["average_cycle_seconds"] is not None]
            bottleneck = max(candidates, key=lambda item: item["average_cycle_seconds"] / item["target_cycle_seconds"], default=None)
            states = ("RUNNING", "STANDBY", "IDLE", "STOPPED", "FAULT", "MANUAL", "DISCONNECTED", "UNKNOWN")
            counts = {state: sum(1 for item in stations if item["state"] == state) for state in states}
            line_cycle = None
            if self.line_cycle_config:
                average = self._line_cycle_total_seconds / self._line_cycle_completed if self._line_cycle_completed else None
                line_cycle = {"target_cycle_seconds": self.line_cycle_config.target_cycle_seconds, "current_cycle_seconds": self._line_cycle_signals.get("CycleTime"), "last_cycle_seconds": self._line_cycle_last_seconds, "average_cycle_seconds": average, "completed_cycles": self._line_cycle_completed, "cycles_over_target": self._line_cycle_over_target}
            return {"line_name": self.line_name, "generated_at": now.isoformat(), "connection": {"connected": all(value[0] for value in self.endpoint_health.values()) and bool(self.endpoint_health), "endpoints": health}, "stations": stations, "line_parts": output_counters[0]["parts_counter"] if len(output_counters) == 1 else None, "line_parts_station": output_counters[0]["name"] if len(output_counters) == 1 else None, "total_parts": sum(item["parts_counter"] or 0 for item in stations), "production_counters": [dict(value) for value in self.line_counters.values()], "line_cycle": line_cycle, "active_alarms": sum(1 for item in stations if item["state"] == "FAULT"), "state_counts": counts, "completed_cycles": sum(item["completed_cycles"] for item in stations), "cycles_over_target": sum(item["cycles_over_target"] for item in stations), "bottleneck": ({"id": bottleneck["id"], "name": bottleneck["name"], "average_cycle_seconds": bottleneck["average_cycle_seconds"], "target_cycle_seconds": bottleneck["target_cycle_seconds"]} if bottleneck else None)}
