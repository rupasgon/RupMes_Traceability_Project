from __future__ import annotations

import json
from urllib.error import URLError
from urllib.request import Request, urlopen


class CentralStoppageSync:
    """Best-effort, outbound-only uploader; local SQLite always remains primary."""

    def __init__(self, store, config, api_key: str):
        self.store, self.config, self.api_key = store, config, api_key

    def run_once(self) -> int:
        events = self.store.pending_stoppage_sync()
        if not events:
            return 0
        payload = {"events": [{
            "source_event_id": event["id"], "line_id": event["line_id"], "station_id": event["station_id"],
            "started_at": event["started_at"], "ended_at": event["ended_at"], "duration_seconds": event["duration_seconds"],
            "reason": event["reason"], "source_state": event["source_state"], "shift": event["shift"],
            "confidence": event["confidence"], "edge_updated_at": event["updated_at"],
        } for event in events]}
        request = Request(
            f"{self.config.base_url.rstrip('/')}/stoppage-events/ingest",
            data=json.dumps(payload).encode("utf-8"), method="POST",
            headers={"Content-Type": "application/json", "Host": self.config.host_header, "X-Client-Id": self.config.client_id, "X-API-Key": self.api_key},
        )
        try:
            with urlopen(request, timeout=10) as response:
                if not 200 <= response.status < 300:
                    return 0
        except (URLError, TimeoutError, OSError):
            return 0
        self.store.mark_stoppages_synced(events)
        return len(events)
