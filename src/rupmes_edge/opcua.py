from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any

from rupmes_edge.config import OpcUaEndpointConfig, secret_from_reference
from rupmes_edge.domain import StationDefinition

logger = logging.getLogger(__name__)
SignalCallback = Callable[[str, str, Any, datetime], Awaitable[None]]
LineSignalCallback = Callable[[str, Any, datetime], Awaitable[None]]
HealthCallback = Callable[[bool, str | None], None]
StateTickCallback = Callable[[datetime], None]


class _SubscriptionHandler:
    def __init__(self, node_metrics: dict[str, tuple[str, str]], callback: SignalCallback):
        self.node_metrics = node_metrics
        self.callback = callback

    def datachange_notification(self, node, value, data) -> None:
        mapping = self.node_metrics.get(node.nodeid.to_string())
        if mapping is None:
            return
        timestamp = getattr(getattr(data, "monitored_item", None), "Value", None)
        observed_at = getattr(timestamp, "SourceTimestamp", None) or datetime.now(timezone.utc)
        asyncio.create_task(self.callback(mapping[0], mapping[1], value, observed_at))


class OpcUaSubscriptionCollector:
    """Long-lived read-only OPC UA polling collector with reconnect backoff.

    The class name is retained for backwards compatibility.  Some PLCs accept
    the initial monitored values but later reject Publish requests with
    BadNoSubscription.  Polling keeps the same configured interval and is much
    more reliable for those servers.
    """

    def __init__(
        self,
        endpoint: OpcUaEndpointConfig,
        stations: list[StationDefinition],
        on_signal: SignalCallback,
        on_health: HealthCallback,
        subscription_interval_ms: int = 500,
        line_node_map: dict[str, str] | None = None,
        on_line_signal: LineSignalCallback | None = None,
        on_state_tick: StateTickCallback | None = None,
    ):
        self.endpoint = endpoint
        self.stations = stations
        self.on_signal = on_signal
        self.on_health = on_health
        self.subscription_interval_ms = subscription_interval_ms
        self.line_node_map = line_node_map or {}
        self.on_line_signal = on_line_signal
        self.on_state_tick = on_state_tick
        self._stopped = asyncio.Event()

    async def run(self) -> None:
        try:
            from asyncua import Client
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("Install the edge extra: pip install -e .[edge]") from exc

        delay_seconds = 1
        while not self._stopped.is_set():
            client = Client(url=self.endpoint.url, timeout=self.endpoint.connect_timeout_seconds)
            try:
                # OPC UA validates that the client certificate SAN URI matches
                # the ApplicationUri included in CreateSession. Set it before
                # asyncua loads and validates the client certificate.
                if self.endpoint.application_uri:
                    client.application_uri = self.endpoint.application_uri
                if self.endpoint.username:
                    password = secret_from_reference(self.endpoint.password_secret_ref)
                    client.set_user(self.endpoint.username)
                    client.set_password(password.get_secret_value() if password else "")
                if self.endpoint.security.policy != "None":
                    security = self.endpoint.security
                    await client.set_security_string(
                        f"{security.policy},{security.mode},{security.client_certificate_path},{security.private_key_path},{security.server_certificate_path}"
                    )
                await client.connect()
                node_metrics: dict[str, list[tuple[str | None, str]]] = {}
                for station in self.stations:
                    for metric, node_id in station.node_map.items():
                        node_metrics.setdefault(node_id, []).append((station.station_id, metric))
                line_nodes = self.line_node_map
                configured_counter_nodes: list[tuple[str, str, str, str]] = []
                for counter in self.endpoint.production_counters:
                    for field, node_id in (("quantity", counter.quantity_node), ("ok", counter.ok_node), ("nok", counter.nok_node)):
                        if node_id:
                            configured_counter_nodes.append((counter.counter_id, counter.name, field, node_id))
                # Current installations already use the PLC's standard
                # OPC_UA.STxx addresses.  Detect that interface so existing
                # configurations immediately expose the three production
                # counters without a configuration-file migration.
                if not line_nodes and not configured_counter_nodes and any("OPC_UA." in node_id for node_id in node_metrics):
                    line_nodes = {
                        "Heartbeat": "ns=4;s=OPC_UA.Heartbeat",
                        "Total": "ns=4;s=OPC_UA.Contador_Total.QTY",
                        "TotalOK": "ns=4;s=OPC_UA.Contador_Total.QTY_OK",
                        "TotalNOK": "ns=4;s=OPC_UA.Contador_Total.QTY_NOK",
                        "WI": "ns=4;s=OPC_UA.Contador_WI.QTY",
                        "WIOK": "ns=4;s=OPC_UA.Contador_WI.QTY_OK",
                        "WINOK": "ns=4;s=OPC_UA.Contador_WI.QTY_NOK",
                        "DI": "ns=4;s=OPC_UA.Contador_DI.QTY",
                        "DIOK": "ns=4;s=OPC_UA.Contador_DI.QTY_OK",
                        "DINOK": "ns=4;s=OPC_UA.Contador_DI.QTY_NOK",
                    }
                for counter_id, counter_name, field, node_id in configured_counter_nodes:
                    node_metrics.setdefault(node_id, []).append(("__line__", f"{counter_id}|{counter_name}|{field}"))
                for metric, node_id in line_nodes.items():
                    legacy = {
                        "Total": ("total", "Total production", "quantity"), "TotalOK": ("total", "Total production", "ok"), "TotalNOK": ("total", "Total production", "nok"),
                        "WI": ("wi", "WI production", "quantity"), "WIOK": ("wi", "WI production", "ok"), "WINOK": ("wi", "WI production", "nok"),
                        "DI": ("di", "DI production", "quantity"), "DIOK": ("di", "DI production", "ok"), "DINOK": ("di", "DI production", "nok"),
                    }
                    if metric in legacy:
                        counter_id, counter_name, field = legacy[metric]
                        node_metrics.setdefault(node_id, []).append(("__line__", f"{counter_id}|{counter_name}|{field}"))
                self.on_health(True, None)
                delay_seconds = 1
                while not self._stopped.is_set():
                    observed_at = datetime.now(timezone.utc)
                    node_ids = list(node_metrics)
                    values = await asyncio.gather(
                        *(client.get_node(node_id).read_value() for node_id in node_ids),
                        return_exceptions=True,
                    )
                    failures = [value for value in values if isinstance(value, Exception)]
                    if failures:
                        raise failures[0]
                    for node_id, value in zip(node_ids, values, strict=True):
                        for station_id, metric in node_metrics[node_id]:
                            if station_id is None:
                                if self.on_line_signal:
                                    await self.on_line_signal(metric, value, observed_at)
                            else:
                                await self.on_signal(station_id, metric, value, observed_at)
                    if self.on_state_tick:
                        self.on_state_tick(observed_at)
                    try:
                        await asyncio.wait_for(self._stopped.wait(), timeout=self.subscription_interval_ms / 1000)
                    except TimeoutError:
                        pass
            except Exception as exc:  # pragma: no cover - depends on network conditions
                message = f"OPC UA connection failed: {exc}"
                logger.warning(message)
                self.on_health(False, message)
                try:
                    await asyncio.wait_for(self._stopped.wait(), timeout=delay_seconds)
                except TimeoutError:
                    delay_seconds = min(delay_seconds * 2, 30)
            finally:
                try:
                    await client.disconnect()
                except Exception:
                    pass

    def stop(self) -> None:
        self._stopped.set()


class LineCycleCollector:
    """Polls a PLC-defined full-piece cycle without treating it as a station."""

    def __init__(self, endpoint, line_cycle, on_signal, on_health, interval_ms: int = 500):
        self.endpoint = endpoint
        self.line_cycle = line_cycle
        self.on_signal = on_signal
        self.on_health = on_health
        self.interval_ms = interval_ms
        self._stopped = asyncio.Event()

    async def run(self) -> None:
        try:
            from asyncua import Client
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("Install the edge extra: pip install -e .[edge]") from exc

        delay_seconds = 1
        while not self._stopped.is_set():
            client = Client(url=self.endpoint.url, timeout=self.endpoint.connect_timeout_seconds)
            try:
                if self.endpoint.username:
                    password = secret_from_reference(self.endpoint.password_secret_ref)
                    client.set_user(self.endpoint.username)
                    client.set_password(password.get_secret_value() if password else "")
                if self.endpoint.security.policy != "None":
                    security = self.endpoint.security
                    await client.set_security_string(
                        f"{security.policy},{security.mode},{security.client_certificate_path},{security.private_key_path},{security.server_certificate_path}"
                    )
                await client.connect()
                cycle_time = client.get_node(self.line_cycle.cycle_time_node)
                cycle_complete = client.get_node(self.line_cycle.cycle_complete_node)
                self.on_health(True, None)
                delay_seconds = 1
                while not self._stopped.is_set():
                    observed_at = datetime.now(timezone.utc)
                    values = await client.read_values([cycle_time, cycle_complete])
                    await self.on_signal("CycleTime", values[0], observed_at)
                    await self.on_signal("CycleComplete", values[1], observed_at)
                    try:
                        await asyncio.wait_for(self._stopped.wait(), timeout=self.interval_ms / 1000)
                    except TimeoutError:
                        pass
            except Exception as exc:  # pragma: no cover - depends on network conditions
                message = f"OPC UA line-cycle connection failed: {exc}"
                logger.warning(message)
                self.on_health(False, message)
                try:
                    await asyncio.wait_for(self._stopped.wait(), timeout=delay_seconds)
                except TimeoutError:
                    delay_seconds = min(delay_seconds * 2, 30)
            finally:
                try:
                    await client.disconnect()
                except Exception:
                    pass

    def stop(self) -> None:
        self._stopped.set()
