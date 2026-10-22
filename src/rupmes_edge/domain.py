from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any


class StationState(StrEnum):
    RUNNING = "RUNNING"
    STANDBY = "STANDBY"
    IDLE = "IDLE"
    STOPPED = "STOPPED"
    FAULT = "FAULT"
    MANUAL = "MANUAL"
    DISCONNECTED = "DISCONNECTED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class StationDefinition:
    station_id: str
    name: str
    target_cycle_seconds: float
    node_map: dict[str, str]
    endpoint_id: str = "default"
    is_output_station: bool = False


@dataclass
class LiveStation:
    definition: StationDefinition
    signals: dict[str, Any] = field(default_factory=dict)
    last_signal_at: datetime | None = None
    last_cycle_seconds: float | None = None
    parts_counter: int | None = None
    completed_cycles: int = 0
    cycles_over_target: int = 0
    _cycle_total_seconds: float = 0.0
    _last_cycle_complete: bool = False
    _last_cycle_complete_at: datetime | None = None

    def apply(self, metric: str, value: Any, observed_at: datetime) -> None:
        self.signals[metric] = value
        self.last_signal_at = observed_at

        if metric == "PartsCounter" and value is not None:
            self.parts_counter = int(value)
        if metric == "CycleComplete":
            is_complete = bool(value)
            if is_complete and not self._last_cycle_complete:
                self._last_cycle_complete_at = observed_at
                self._record_cycle()
            self._last_cycle_complete = is_complete

    def _record_cycle(self) -> None:
        raw_cycle_time = self.signals.get("CycleTime")
        if raw_cycle_time is None:
            return
        self.last_cycle_seconds = float(raw_cycle_time)
        self.completed_cycles += 1
        self._cycle_total_seconds += self.last_cycle_seconds
        if self.last_cycle_seconds > self.definition.target_cycle_seconds:
            self.cycles_over_target += 1

    def state(self, endpoint_connected: bool, now: datetime, stale_after_seconds: float = 5.0) -> StationState:
        if not endpoint_connected or self.last_signal_at is None:
            return StationState.DISCONNECTED
        age_seconds = (now - self.last_signal_at).total_seconds()
        if age_seconds > stale_after_seconds:
            return StationState.DISCONNECTED
        if bool(self.signals.get("FaultActive")) or self.signals.get("AlarmCode") not in (None, "", 0, "0"):
            return StationState.FAULT
        if self.signals.get("AutoMode") is False:
            return StationState.MANUAL
        # PLC Running often means enabled/ready.  It is not sufficient proof
        # of production: a station is green only during an active cycle or
        # shortly after a completed cycle.
        if self.signals.get("CycleActive") is True:
            return StationState.RUNNING
        recent_cycle_window = max(self.definition.target_cycle_seconds * 1.5, 5.0)
        if self._last_cycle_complete_at and (now - self._last_cycle_complete_at).total_seconds() <= recent_cycle_window:
            return StationState.RUNNING
        if self.signals.get("Running") is True:
            return StationState.STANDBY
        if self.signals.get("Running") is False:
            return StationState.IDLE
        return StationState.UNKNOWN

    def as_dict(self, endpoint_connected: bool, now: datetime) -> dict[str, Any]:
        state = self.state(endpoint_connected, now)
        average = self._cycle_total_seconds / self.completed_cycles if self.completed_cycles else None
        last_update = self.last_signal_at.isoformat() if self.last_signal_at else None
        return {
            "id": self.definition.station_id,
            "name": self.definition.name,
            "state": state.value,
            "target_cycle_seconds": self.definition.target_cycle_seconds,
            "last_cycle_seconds": self.last_cycle_seconds,
            "current_cycle_seconds": self.signals.get("CycleTime"),
            "average_cycle_seconds": average,
            "cycle_deviation_seconds": (
                self.last_cycle_seconds - self.definition.target_cycle_seconds
                if self.last_cycle_seconds is not None
                else None
            ),
            "parts_counter": self.parts_counter,
            "is_output_station": self.definition.is_output_station,
            "completed_cycles": self.completed_cycles,
            "cycles_over_target": self.cycles_over_target,
            "alarm_code": self.signals.get("AlarmCode"),
            "auto_mode": self.signals.get("AutoMode"),
            "running": self.signals.get("Running"),
            "last_update": last_update,
        }


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
