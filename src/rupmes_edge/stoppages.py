"""Durable, debounced stoppage events derived from station state."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any


STOPPING_STATES = {"DISCONNECTED", "FAULT", "MANUAL", "STOPPED", "IDLE"}


@dataclass(frozen=True)
class StoppagePolicy:
    """Thresholds used to prevent poll-to-poll state noise becoming downtime."""

    open_after_seconds: float = 5.0
    close_after_seconds: float = 3.0
    micro_stop_seconds: float = 60.0


def reason_for_state(state: str) -> str | None:
    return {
        "DISCONNECTED": "COMMUNICATION_LOSS",
        "FAULT": "FAULT",
        "MANUAL": "MANUAL",
        "STOPPED": "STOPPED",
        "IDLE": "WAITING",
    }.get(state)


def classification_for(reason: str, station: dict[str, Any]) -> tuple[str, float]:
    """Return the automatic classification and the evidence-based confidence."""
    if reason == "FAULT":
        return "AUTOMATIC", 0.95 if station.get("active_alarm_sources") or station.get("alarm_code") else 0.80
    if reason == "MANUAL":
        return "AUTOMATIC", 0.95
    if reason == "COMMUNICATION_LOSS":
        return "AUTOMATIC", 0.90
    if reason == "STOPPED":
        return "AUTOMATIC", 0.75
    return "AUTOMATIC", 0.60


class StoppageTracker:
    """One-station state machine that owns at most one open stoppage event."""

    def __init__(self, station_id: str, store, line_id: str, timezone_name: str, policy: StoppagePolicy):
        self.station_id = station_id
        self.store = store
        self.line_id = line_id
        self.timezone_name = timezone_name
        self.policy = policy
        self.open_event: dict[str, Any] | None = None
        self._candidate_reason: str | None = None
        self._candidate_since: datetime | None = None

    def restore(self, event: dict[str, Any]) -> None:
        """Adopt an event left open by the previous Edge process."""
        self.open_event = event

    def observe(self, state: str, station: dict[str, Any], observed_at: datetime) -> None:
        desired_reason = reason_for_state(state)
        if desired_reason is None and not self.open_event:
            self._clear_candidate()
            return
        if self.open_event and desired_reason == self.open_event["reason"]:
            self._clear_candidate()
            return
        if self._candidate_since is None:
            self._candidate_reason = desired_reason
            self._candidate_since = observed_at
            return
        changed_candidate = desired_reason != self._candidate_reason
        if changed_candidate:
            self._candidate_reason = desired_reason
            self._candidate_since = observed_at
            # A confirmed endpoint failure is already a reliable external
            # condition; it must not wait for a later PLC poll that may never
            # arrive while the endpoint remains down.
            if desired_reason != "COMMUNICATION_LOSS":
                return
        if self._candidate_since is None:
            self._candidate_since = observed_at
            return

        threshold = 0.0 if desired_reason == "COMMUNICATION_LOSS" and not self.open_event else (
            self.policy.close_after_seconds if self.open_event else self.policy.open_after_seconds
        )
        if observed_at - self._candidate_since < timedelta(seconds=threshold):
            return

        transition_at = self._candidate_since
        if self.open_event:
            self.store.close_stoppage(self.open_event["id"], transition_at)
            self.open_event = None
        if desired_reason:
            classification, confidence = classification_for(desired_reason, station)
            self.open_event = self.store.open_stoppage(
                line_id=self.line_id,
                station_id=self.station_id,
                reason=desired_reason,
                source_state=state,
                started_at=transition_at,
                shift=self.store.shift_at(transition_at, self.timezone_name),
                classification=classification,
                confidence=confidence,
                alarm_ids=[item["id"] for item in station.get("active_alarm_sources", [])],
                alarm_code=station.get("alarm_code"),
            )
        self._clear_candidate()

    def _clear_candidate(self) -> None:
        self._candidate_reason = None
        self._candidate_since = None
