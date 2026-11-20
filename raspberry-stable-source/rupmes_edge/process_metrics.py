"""Additional per-station process-duration metrics.

Kept as a small adapter around the stable runtime so it can be deployed without
changing the existing SQLite/history implementation.
"""

from __future__ import annotations

import json
from contextlib import nullcontext
from pathlib import Path
from typing import Any


TARGETS_PATH = Path("/var/lib/rupmes-edge/process-cycle-targets.json")


def enable_process_metrics(runtime: Any) -> None:
    if getattr(runtime, "_process_metrics_enabled", False):
        return
    runtime._process_metrics_enabled = True
    runtime.process_cycle_values: dict[str, float | None] = {}
    runtime.process_cycle_targets: dict[str, float] = {}

    try:
        stored = json.loads(TARGETS_PATH.read_text(encoding="utf-8"))
        if isinstance(stored, dict):
            runtime.process_cycle_targets = {
                str(station_id): float(target)
                for station_id, target in stored.items()
                if float(target) > 0
            }
    except (FileNotFoundError, ValueError, TypeError):
        pass

    for station_id, station in runtime.stations.items():
        runtime.process_cycle_targets.setdefault(
            station_id, float(station.definition.target_cycle_seconds)
        )

    original_apply = runtime.apply_update
    original_snapshot = runtime.snapshot

    async def apply_update(station_id: str, signal: str, value: Any, observed_at: Any) -> None:
        if signal == "ProcessCycleTime":
            try:
                measured = float(value)
            except (TypeError, ValueError):
                return
            lock = getattr(runtime, "_lock", None)
            with lock if lock is not None else nullcontext():
                runtime.process_cycle_values[station_id] = measured
            return
        await original_apply(station_id, signal, value, observed_at)

    def snapshot() -> dict[str, Any]:
        payload = original_snapshot()
        lock = getattr(runtime, "_lock", None)
        with lock if lock is not None else nullcontext():
            values = dict(runtime.process_cycle_values)
            targets = dict(runtime.process_cycle_targets)
        for station in payload.get("stations", []):
            station_id = station["id"]
            duration = values.get(station_id)
            target = targets.get(station_id)
            station["process_cycle_seconds"] = duration
            station["process_target_seconds"] = target
            station["process_deviation_seconds"] = (
                duration - target if duration is not None and target is not None else None
            )
        return payload

    def process_targets() -> dict[str, float]:
        return dict(runtime.process_cycle_targets)

    def set_process_targets(values: dict[str, Any]) -> dict[str, float]:
        updated: dict[str, float] = {}
        for station_id, value in values.items():
            if station_id not in runtime.stations:
                continue
            try:
                target = float(value)
            except (TypeError, ValueError):
                continue
            if target > 0:
                updated[station_id] = target
        lock = getattr(runtime, "_lock", None)
        with lock if lock is not None else nullcontext():
            runtime.process_cycle_targets.update(updated)
            TARGETS_PATH.parent.mkdir(parents=True, exist_ok=True)
            TARGETS_PATH.write_text(
                json.dumps(runtime.process_cycle_targets, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            return dict(runtime.process_cycle_targets)

    runtime.apply_update = apply_update
    runtime.snapshot = snapshot
    runtime.get_process_targets = process_targets
    runtime.set_process_targets = set_process_targets
