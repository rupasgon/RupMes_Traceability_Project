from __future__ import annotations

import json
from urllib.error import URLError
from urllib.request import Request, urlopen


class CentralStoppageSync:
    """Best-effort, outbound-only Edge uploader; local SQLite remains primary."""

    def __init__(self, store, config, api_key: str):
        self.store, self.config, self.api_key = store, config, api_key

    def run_once(self) -> int:
        delivered = self._sync_stoppages()
        delivered += self._sync_production_counters()
        return delivered

    def _post(self, path: str, payload: dict) -> bool:
        request = Request(
            f"{self.config.base_url.rstrip('/')}{path}", data=json.dumps(payload).encode("utf-8"), method="POST",
            headers={"Content-Type": "application/json", "Host": self.config.host_header, "X-Client-Id": self.config.client_id, "X-API-Key": self.api_key},
        )
        try:
            with urlopen(request, timeout=10) as response:
                return 200 <= response.status < 300
        except (URLError, TimeoutError, OSError):
            return False

    def _sync_stoppages(self) -> int:
        events = self.store.pending_stoppage_sync()
        if not events:
            return 0
        payload = {"events": [{
            "source_event_id": event["id"], "line_id": event["line_id"], "station_id": event["station_id"],
            "started_at": event["started_at"], "ended_at": event["ended_at"], "duration_seconds": event["duration_seconds"],
            "reason": event["reason"], "source_state": event["source_state"], "shift": event["shift"],
            "confidence": event["confidence"], "edge_updated_at": event["updated_at"],
        } for event in events]}
        if not self._post("/stoppage-events/ingest", payload):
            return 0
        self.store.mark_stoppages_synced(events)
        return len(events)

    def _sync_production_counters(self) -> int:
        events = self.store.pending_production_counter_sync()
        if not events:
            return 0
        payload = {"events": [{
            "source_event_id": event["id"], "line_id": event["line_id"], "counter_id": event["counter_id"], "counter_name": event["counter_name"], "counter_epoch": event["counter_epoch"], "observed_at": event["observed_at"], "quantity": event["quantity"], "ok_quantity": event["ok_quantity"], "nok_quantity": event["nok_quantity"], "delta_quantity": event["delta_quantity"], "delta_ok": event["delta_ok"], "delta_nok": event["delta_nok"], "reset_detected": bool(event["reset_detected"]),
        } for event in events]}
        if not self._post("/production-counter-events/ingest", payload):
            return 0
        self.store.mark_production_counters_synced(events)
        return len(events)
