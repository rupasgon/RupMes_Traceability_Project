from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class StoppagePolicy:
    open_after_seconds: float = 5.0
    close_after_seconds: float = 3.0
    micro_stop_seconds: float = 60.0


def reason_for(state: str) -> str | None:
    return {"DISCONNECTED": "COMMUNICATION_LOSS", "FAULT": "FAULT", "MANUAL": "MANUAL", "STOPPED": "STOPPED", "IDLE": "WAITING"}.get(state)


class StoppageTracker:
    def __init__(self, station_id, store, line_id, timezone_name, policy):
        self.station_id, self.store, self.line_id, self.timezone_name, self.policy = station_id, store, line_id, timezone_name, policy
        self.open_event = None
        self.candidate = None
        self.candidate_since = None

    def restore(self, event):
        self.open_event = event

    def observe(self, state, station, observed_at):
        desired = reason_for(state)
        if desired is None and not self.open_event:
            self.candidate = self.candidate_since = None
            return
        if self.open_event and desired == self.open_event["reason"]:
            self.candidate = self.candidate_since = None
            return
        if self.candidate_since is None:
            self.candidate, self.candidate_since = desired, observed_at
            return
        if desired != self.candidate:
            self.candidate, self.candidate_since = desired, observed_at
            if desired != "COMMUNICATION_LOSS":
                return
        threshold = 0 if desired == "COMMUNICATION_LOSS" and not self.open_event else (self.policy.close_after_seconds if self.open_event else self.policy.open_after_seconds)
        if observed_at - self.candidate_since < timedelta(seconds=threshold):
            return
        transition_at = self.candidate_since
        if self.open_event:
            self.store.close_stoppage(self.open_event["id"], transition_at)
            self.open_event = None
        if desired:
            confidence = 0.95 if desired == "MANUAL" else 0.90 if desired == "COMMUNICATION_LOSS" else 0.80 if desired == "FAULT" else 0.60
            self.open_event = self.store.open_stoppage(self.line_id, self.station_id, desired, state, transition_at, self.store.shift_at(transition_at, self.timezone_name), confidence)
        self.candidate = self.candidate_since = None
