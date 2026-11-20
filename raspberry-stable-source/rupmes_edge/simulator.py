from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from rupmes_edge.config import SIMULATOR_ENDPOINT, demo_config


@dataclass
class SimulatedStation:
    station_id: str
    cycle_time: float
    counter: int = 0
    variables: dict[str, Any] = field(default_factory=dict)


async def run_simulator(endpoint_url: str = SIMULATOR_ENDPOINT) -> None:
    try:
        from asyncua import Server, ua
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Install the edge extra: pip install -e .[edge]") from exc

    server = Server()
    await server.init()
    server.set_endpoint(endpoint_url)
    namespace_index = await server.register_namespace("urn:rupmes:edge:simulator")
    stations = [
        SimulatedStation("ST01", 17.2),
        SimulatedStation("ST02", 23.4),
        SimulatedStation("ST03", 20.8),
        SimulatedStation("ST04", 15.5),
    ]
    station_nodes: dict[str, dict[str, Any]] = {}

    for definition, station in zip(demo_config().station_definitions(), stations, strict=True):
        folder = await server.nodes.objects.add_object(
            ua.NodeId(f"Stations.{station.station_id}", namespace_index), definition.name
        )
        initial_values = {
            "Running": False,
            "CycleActive": False,
            "CycleComplete": False,
            "CycleTime": station.cycle_time,
            "PartsCounter": station.counter,
            "FaultActive": False,
            "AutoMode": True,
            "AlarmCode": "",
            "Heartbeat": 0,
        }
        station_nodes[station.station_id] = {}
        for metric, value in initial_values.items():
            node = await folder.add_variable(ua.NodeId(f"Stations.{station.station_id}.{metric}", namespace_index), metric, value)
            station_nodes[station.station_id][metric] = node
            station.variables[metric] = value

    async with server:
        tick = 0
        while True:
            tick += 1
            for index, station in enumerate(stations):
                phase = (tick + index * 3) % 20
                fault = station.station_id == "ST03" and 15 <= phase <= 17
                manual = station.station_id == "ST04" and phase == 18
                running = not fault and not manual and phase not in (0, 1)
                cycle_complete = running and phase in (6, 13)
                if cycle_complete:
                    station.counter += 1
                cycle_time = station.cycle_time + ((tick + index) % 5 - 2) * 0.45
                values = {
                    "Running": running,
                    "CycleActive": running and phase not in (6, 13),
                    "CycleComplete": cycle_complete,
                    "CycleTime": round(cycle_time, 2),
                    "PartsCounter": station.counter,
                    "FaultActive": fault,
                    "AutoMode": not manual,
                    "AlarmCode": "E-201" if fault else "",
                    "Heartbeat": tick,
                }
                for metric, value in values.items():
                    if station.variables.get(metric) != value:
                        await station_nodes[station.station_id][metric].write_value(value)
                        station.variables[metric] = value
            await asyncio.sleep(1)
