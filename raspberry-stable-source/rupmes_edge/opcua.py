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
HealthCallback = Callable[[bool, str | None], None]


class _SubscriptionHandler:
    def __init__(self, node_metrics: dict[str, tuple[str, str]], callback: SignalCallback):
        self.node_metrics = node_metrics
        self.callback = callback

    def datachange_notification(self, node, value, data) -> None:
        mapping = self.node_metrics.get(node.nodeid.to_string())
        if mapping is None:
            return
        # Some PLCs publish local wall-clock time but label it as UTC.  The
        # value is then in the future on the Edge and prevents stale-signal
        # detection (and incident timers) from working.  For operational
        # freshness, receipt time at the Edge is the authoritative timestamp.
        observed_at = datetime.now(timezone.utc)
        asyncio.create_task(self.callback(mapping[0], mapping[1], value, observed_at))


class OpcUaSubscriptionCollector:
    """Long-lived read-only OPC UA subscription collector with reconnect backoff."""

    def __init__(
        self,
        endpoint: OpcUaEndpointConfig,
        stations: list[StationDefinition],
        on_signal: SignalCallback,
        on_health: HealthCallback,
        subscription_interval_ms: int = 500,
    ):
        self.endpoint = endpoint
        self.stations = stations
        self.on_signal = on_signal
        self.on_health = on_health
        self.subscription_interval_ms = subscription_interval_ms
        self._stopped = asyncio.Event()

    async def run(self) -> None:
        try:
            from asyncua import Client
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("Install the edge extra: pip install -e .[edge]") from exc

        delay_seconds = 1
        while not self._stopped.is_set():
            client = Client(url=self.endpoint.url, timeout=self.endpoint.connect_timeout_seconds)
            subscription = None
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
                node_metrics: list[tuple[str, str]] = []
                nodes = []
                for station in self.stations:
                    for metric, node_id in station.node_map.items():
                        node = client.get_node(node_id)
                        nodes.append(node)
                        node_metrics.append((station.station_id, metric))
                self.on_health(True, None)
                delay_seconds = 1
                # BMW's server intermittently returns BadNoSubscription after
                # accepting a subscription.  Batched reads keep the same
                # configured cadence while avoiding PublishRequest failures.
                while not self._stopped.is_set():
                    observed_at = datetime.now(timezone.utc)
                    values = await client.read_values(nodes)
                    for (station_id, metric), value in zip(node_metrics, values, strict=True):
                        await self.on_signal(station_id, metric, value, observed_at)
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
                if subscription is not None:
                    try:
                        await subscription.delete()
                    except Exception:
                        pass
                try:
                    await client.disconnect()
                except Exception:
                    pass

    def stop(self) -> None:
        self._stopped.set()


class MetricPollCollector:
    """Small read-only poller for line KPIs that are not station signals."""
    def __init__(self, endpoint, node_map, callback, on_health, interval_ms=500):
        self.endpoint, self.node_map, self.callback, self.on_health = endpoint, node_map, callback, on_health
        self.interval_ms, self._stopped = interval_ms, asyncio.Event()

    async def run(self) -> None:
        from asyncua import Client
        delay = 1
        while not self._stopped.is_set():
            client = Client(url=self.endpoint.url, timeout=self.endpoint.connect_timeout_seconds)
            client.application_uri = self.endpoint.application_uri
            try:
                if self.endpoint.username:
                    password = secret_from_reference(self.endpoint.password_secret_ref)
                    client.set_user(self.endpoint.username)
                    client.set_password(password.get_secret_value() if password else "")
                if self.endpoint.security.policy != "None":
                    security = self.endpoint.security
                    await client.set_security_string(f"{security.policy},{security.mode},{security.client_certificate_path},{security.private_key_path},{security.server_certificate_path}")
                await client.connect()
                nodes = {metric: client.get_node(node_id) for metric, node_id in self.node_map.items()}
                self.on_health(True, None)
                delay = 1
                while not self._stopped.is_set():
                    timestamp = datetime.now(timezone.utc)
                    values = await client.read_values(list(nodes.values()))
                    for metric, value in zip(nodes, values, strict=True):
                        await self.callback(metric, value, timestamp)
                    try:
                        await asyncio.wait_for(self._stopped.wait(), timeout=self.interval_ms / 1000)
                    except TimeoutError:
                        pass
            except Exception as exc:
                self.on_health(False, f"OPC UA metric polling failed: {exc}")
                try:
                    await asyncio.wait_for(self._stopped.wait(), timeout=delay)
                except TimeoutError:
                    delay = min(delay * 2, 30)
            finally:
                try:
                    await client.disconnect()
                except Exception:
                    pass

    def stop(self) -> None:
        self._stopped.set()
