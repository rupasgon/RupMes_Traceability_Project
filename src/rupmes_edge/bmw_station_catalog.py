"""Authoritative physical layout for the BMW assembly line.

The catalogue is intentionally separate from OPC UA connection settings: a
station can be shown with its process and physical description without
changing a production endpoint, certificate or NodeId configuration.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BmwStationMetadata:
    station_id: str
    process_id: str
    description: str
    order: int
    opcua_pending: bool = False


def _station(station_id: str, process_id: str, description: str, order: int, *, opcua_pending: bool = False) -> BmwStationMetadata:
    return BmwStationMetadata(station_id, process_id, description, order, opcua_pending)


# Source of truth: the validated BMW physical station table supplied by the
# production team. ST34 is deliberately present but marked pending until its
# OPC UA tags are confirmed; ST33 is not part of this physical layout.
BMW_STATION_CATALOG = {
    item.station_id: item
    for item in (
        _station("ST01", "P200", "Load and assembly DI button into the DI knob", 1),
        _station("ST29", "P200", "Cleaning of the pallet", 2),
        _station("ST02", "P202", "Load of the DI lever cover into the pallet", 3),
        _station("ST03", "P204", "Load of the WI lever cover into the pallet", 4),
        _station("ST04", "P206", "Load of the DI lever housing into the pallet", 5),
        _station("ST05", "P208", "Load of the WI knob into the pallet", 6),
        _station("ST06", "P210", "DI rotator greasing and load into the pallet", 7),
        _station("ST07", "P212", "Plunger assembly into DI rotator", 8),
        _station("ST08", "P214", "Hub greasing and assembly into the pallet", 9),
        _station("ST09", "P216", "DI actuator assembly into the pallet", 10),
        _station("ST10", "P218", "DI long button assembly into the pallet", 11),
        _station("ST11", "P220", "Keypads assembly", 12),
        _station("ST12", "P222", "Knob DI PCB greasing and assembly into the pallet", 13),
        _station("ST13", "P224", "Hub WI greasing and assembly into the pallet", 14),
        _station("ST14", "P226", "Plunger assembly into the hub WI", 15),
        _station("ST15", "P228", "Core WI greasing and assembly into the pallet", 16),
        _station("ST16", "P230", "Small plunger assembly into the core", 17),
        _station("ST17", "P232", "Turn table - contact spring", 18),
        _station("ST18", "P234", "WI knob PCB greasing and assembly into the pallet", 19),
        _station("ST19", "P236", "DI long button PCB assembly into the pallet", 20),
        _station("ST20", "P238", "Slider WI assembly into sub-assembly", 21),
        _station("ST21", "P240", "Cold riveting of Housing lever DI to DI long button PCB", 22),
        _station("ST22", "P242", "Manual Station 1", 23),
        _station("ST23", "P244", "Manual Station 2", 24),
        _station("ST24", "P246", "Manual Station 3", 25),
        _station("ST25", "P248", "Harness routing visual inspection", 26),
        _station("ST26", "P250", "WI housing assembly into pallet and clipping", 27),
        _station("ST31", "P250", "Pressing machine", 28),
        _station("ST28", "P252", "Lever DI clipping", 29),
        _station("ST32", "P252", "Pressing machine", 30),
        _station("ST34", "P254", "Turn table - magnets + pivot", 31, opcua_pending=True),
    )
}


def get_bmw_station_metadata(station_id: str) -> BmwStationMetadata | None:
    """Return physical metadata without making OPC UA configuration mandatory."""
    return BMW_STATION_CATALOG.get(station_id.upper())
