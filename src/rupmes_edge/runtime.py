from __future__ import annotations

from datetime import datetime
from threading import RLock
import threading
from typing import Any

from rupmes_edge.domain import LiveStation, StationDefinition, utc_now


class EdgeRuntime:
    def __init__(self, line_name: str, stations: list[StationDefinition], store=None, line_cycle_config=None):
        self.line_name = line_name
        self._lock = RLock()
        self.stations = {definition.station_id: LiveStation(definition) for definition in stations}
        self.endpoint_health: dict[str, tuple[bool, str | None]] = {}
        self.store = store
        self._last_states: dict[str, str] = {}
        self.line_cycle_config = line_cycle_config
        self._line_cycle_signals: dict[str, Any] = {}
        self._line_cycle_last_complete = False
        self._line_cycle_last_seconds: float | None = None
        self._line_cycle_completed = 0
        self._line_cycle_over_target = 0
        self._line_cycle_total_seconds = 0.0
        self._last_counters: dict[str, float] = {}
        self.line_counters: dict[str, dict[str, Any]] = {}

    async def apply_line_cycle_update(self, metric: str, value: Any, observed_at: datetime) -> None:
        """Record an optional, PLC-defined full-piece cycle on a rising completion edge."""
        self._line_cycle_signals[metric] = value
        if metric != "CycleComplete":
            return
        is_complete = bool(value)
        if is_complete and not self._line_cycle_last_complete:
            raw_cycle_time = self._line_cycle_signals.get("CycleTime")
            try:
                seconds = float(raw_cycle_time)
            except (TypeError, ValueError):
                seconds = None
            if seconds is not None:
                self._line_cycle_last_seconds = seconds
                self._line_cycle_completed += 1
                self._line_cycle_total_seconds += seconds
                if self.line_cycle_config and seconds > self.line_cycle_config.target_cycle_seconds:
                    self._line_cycle_over_target += 1
        self._line_cycle_last_complete = is_complete

    async def apply_update(self, station_id: str, metric: str, value: Any, observed_at: datetime) -> None:
        if station_id == "__line__":
            await self.apply_line_update(metric, value, observed_at)
            return
        with self._lock:
            station = self.stations[station_id]
            previous_cycles = station.completed_cycles
            station.apply(metric, value, observed_at)
            if self.store and station.completed_cycles > previous_cycles and station.last_cycle_seconds is not None:
                self.store.record_cycle(station_id, station.last_cycle_seconds, observed_at)
            if self.store and metric == "PartsCounter":
                try:
                    counter = float(value)
                    if self._last_counters.get(station_id) != counter:
                        self.store.record_counter(station_id, counter, observed_at)
                        self._last_counters[station_id] = counter
                except (TypeError, ValueError):
                    pass
            # The collector is the sole writer of state transitions.  This
            # makes page refreshes read-only and safe for many viewers.
            self.capture_states(station.definition.endpoint_id, observed_at)

    async def apply_line_update(self, metric: str, value: Any, observed_at: datetime) -> None:
        """Apply a production counter read from the line-level OPC UA interface."""
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return
        with self._lock:
            parts = metric.split("|", 2)
            if len(parts) == 3:
                counter_id, name, field = parts
            else:
                counter_id, name, field = metric, metric, "quantity"
            counter = self.line_counters.setdefault(
                counter_id,
                {
                    "id": counter_id,
                    "name": name,
                    "quantity": None,
                    "ok": None,
                    "nok": None,
                    "pieces_per_hour": None,
                    "_rate_start_quantity": None,
                    "_rate_start_at": None,
                },
            )
            counter[field] = numeric
            if field == "quantity":
                start_quantity = counter["_rate_start_quantity"]
                start_at = counter["_rate_start_at"]
                # PLC restarts can reset a totalizer. Start a fresh average rather
                # than publishing a negative production rate in that case.
                if start_quantity is None or start_at is None or numeric < start_quantity:
                    counter["_rate_start_quantity"] = numeric
                    counter["_rate_start_at"] = observed_at
                    counter["pieces_per_hour"] = None
                else:
                    elapsed_seconds = (observed_at - start_at).total_seconds()
                    counter["pieces_per_hour"] = (
                        (numeric - start_quantity) * 3600 / elapsed_seconds
                        if elapsed_seconds > 0
                        else None
                    )

    def capture_states(self, endpoint_id: str, observed_at: datetime) -> None:
        """Persist state transitions only from the collector, never from HTTP reads."""
        with self._lock:
            connected = self.endpoint_health.get(endpoint_id, (False, None))[0]
            for station in self.stations.values():
                if station.definition.endpoint_id != endpoint_id:
                    continue
                item = station.as_dict(connected, observed_at)
                state = item["state"]
                station_id = station.definition.station_id
                if self.store and self._last_states.get(station_id) != state:
                    detail = str(item["alarm_code"]) if state == "FAULT" and item["alarm_code"] not in (None, "", 0, "0") else ("Fault active" if state == "FAULT" else None)
                    self.store.record_state(station_id, state, observed_at, detail)
                self._last_states[station_id] = state

    def set_endpoint_health(self, endpoint_id: str, connected: bool, error: str | None = None) -> None:
        with self._lock:
            previous = self.endpoint_health.get(endpoint_id)
            self.endpoint_health[endpoint_id] = (connected, error)
            if self.store and previous != (connected, error):
                self.store.record_connector(endpoint_id, connected, error, utc_now())

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            now = utc_now()
            stations = []
            for station in self.stations.values():
                connected = self.endpoint_health.get(station.definition.endpoint_id, (False, None))[0]
                stations.append(station.as_dict(connected, now))
            health = {endpoint_id: {"connected": value[0], "error": value[1]} for endpoint_id, value in self.endpoint_health.items()}
            line_counters = [
                {key: value for key, value in counter.items() if not key.startswith("_")}
                for counter in self.line_counters.values()
            ]
        output_counters = [item for item in stations if item["is_output_station"] and item["parts_counter"] is not None]
        bottleneck_candidates = [item for item in stations if item["average_cycle_seconds"] is not None]
        bottleneck = max(
            bottleneck_candidates,
            key=lambda item: item["average_cycle_seconds"] / item["target_cycle_seconds"],
            default=None,
        )
        state_counts = {state: sum(1 for item in stations if item["state"] == state) for state in ("RUNNING", "STANDBY", "IDLE", "STOPPED", "FAULT", "MANUAL", "DISCONNECTED", "UNKNOWN")}
        line_cycle = None
        if self.line_cycle_config:
            endpoint_connected = self.endpoint_health.get(self.line_cycle_config.endpoint_id, (False, None))[0]
            average = self._line_cycle_total_seconds / self._line_cycle_completed if self._line_cycle_completed else None
            line_cycle = {
                "configured": True,
                "connected": endpoint_connected,
                "target_cycle_seconds": self.line_cycle_config.target_cycle_seconds,
                "current_cycle_seconds": self._line_cycle_signals.get("CycleTime"),
                "last_cycle_seconds": self._line_cycle_last_seconds,
                "average_cycle_seconds": average,
                "completed_cycles": self._line_cycle_completed,
                "cycles_over_target": self._line_cycle_over_target,
                "cycle_active": self._line_cycle_signals.get("CycleActive"),
                "cycle_complete": self._line_cycle_signals.get("CycleComplete"),
            }
        return {
            "line_name": self.line_name,
            "generated_at": now.isoformat(),
            "connection": {"connected": all(value[0] for value in self.endpoint_health.values()) and bool(self.endpoint_health), "endpoints": health},
            "stations": stations,
            "line_parts": output_counters[0]["parts_counter"] if len(output_counters) == 1 else None,
            "line_parts_station": output_counters[0]["name"] if len(output_counters) == 1 else None,
            "production_counters": line_counters,
            "total_parts": sum(item["parts_counter"] or 0 for item in stations),
            "active_alarms": sum(1 for item in stations if item["state"] == "FAULT"),
            "state_counts": state_counts,
            "completed_cycles": sum(item["completed_cycles"] for item in stations),
            "cycles_over_target": sum(item["cycles_over_target"] for item in stations),
            "bottleneck": (
                {
                    "id": bottleneck["id"],
                    "name": bottleneck["name"],
                    "average_cycle_seconds": bottleneck["average_cycle_seconds"],
                    "target_cycle_seconds": bottleneck["target_cycle_seconds"],
                }
                if bottleneck
                else None
            ),
            "line_cycle": line_cycle,
        }
