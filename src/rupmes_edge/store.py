from __future__ import annotations

import sqlite3
import threading
import json
import uuid
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


class EdgeStore:
    """SQLite event store and local operational configuration."""

    def __init__(self, database_path: str | Path):
        self.path = Path(database_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # A dashboard request is served by a worker thread while the OPC UA
        # collector runs in the event-loop thread.  SQLite connections may be
        # shared only when access is serialised by us.
        self._lock = threading.RLock()
        self.connection = sqlite3.connect(self.path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS station_state_events (id INTEGER PRIMARY KEY, station_id TEXT NOT NULL, state TEXT NOT NULL, detail TEXT, observed_at TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS ix_station_state_events_station_time ON station_state_events(station_id, observed_at);
            CREATE TABLE IF NOT EXISTS cycle_events (id INTEGER PRIMARY KEY, station_id TEXT NOT NULL, cycle_seconds REAL NOT NULL, observed_at TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS ix_cycle_events_station_time ON cycle_events(station_id, observed_at);
            CREATE TABLE IF NOT EXISTS connector_events (id INTEGER PRIMARY KEY, endpoint_id TEXT NOT NULL, connected INTEGER NOT NULL, detail TEXT, observed_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS counter_events (id INTEGER PRIMARY KEY, station_id TEXT NOT NULL, parts_counter REAL NOT NULL, observed_at TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS ix_counter_events_station_time ON counter_events(station_id, observed_at);
            CREATE TABLE IF NOT EXISTS signal_events (id INTEGER PRIMARY KEY, station_id TEXT NOT NULL, signal TEXT NOT NULL, old_value TEXT, new_value TEXT, observed_at TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS ix_signal_events_station_time ON signal_events(station_id, observed_at);
            CREATE TABLE IF NOT EXISTS fault_events (id INTEGER PRIMARY KEY, station_id TEXT NOT NULL, alarm_id TEXT NOT NULL, category TEXT NOT NULL, description TEXT, active INTEGER NOT NULL, observed_at TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS ix_fault_events_station_time ON fault_events(station_id, observed_at);
            CREATE TABLE IF NOT EXISTS edge_configuration (id INTEGER PRIMARY KEY CHECK (id = 1), payload TEXT NOT NULL, updated_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS stoppage_events (
                id TEXT PRIMARY KEY,
                line_id TEXT NOT NULL,
                station_id TEXT NOT NULL,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                duration_seconds REAL,
                reason TEXT NOT NULL,
                source_state TEXT NOT NULL,
                shift TEXT NOT NULL,
                classification TEXT NOT NULL,
                confidence REAL NOT NULL,
                alarm_ids TEXT NOT NULL DEFAULT '[]',
                alarm_code TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS ix_stoppage_events_station_started ON stoppage_events(station_id, started_at);
            CREATE INDEX IF NOT EXISTS ix_stoppage_events_line_started ON stoppage_events(line_id, started_at);
            CREATE UNIQUE INDEX IF NOT EXISTS ux_stoppage_events_open_station ON stoppage_events(station_id) WHERE ended_at IS NULL;
        """)
        # Existing installations created the table before the detail column
        # existed.  Keep this migration deliberately small and idempotent.
        try:
            self.connection.execute("ALTER TABLE station_state_events ADD COLUMN detail TEXT")
        except sqlite3.OperationalError:
            pass
        self.connection.commit()

    def load_configuration(self) -> str | None:
        row = self.connection.execute("SELECT payload FROM edge_configuration WHERE id = 1").fetchone()
        return str(row[0]) if row else None

    def save_configuration(self, payload: str) -> None:
        self.connection.execute(
            "INSERT INTO edge_configuration(id, payload, updated_at) VALUES (1, ?, ?) ON CONFLICT(id) DO UPDATE SET payload = excluded.payload, updated_at = excluded.updated_at",
            (payload, datetime.now(timezone.utc).isoformat()),
        )
        self.connection.commit()

    def record_state(self, station_id: str, state: str, observed_at: datetime, detail: str | None = None) -> None:
        with self._lock:
            self.connection.execute(
                "INSERT INTO station_state_events(station_id, state, detail, observed_at) VALUES (?, ?, ?, ?)",
                (station_id, state, detail, observed_at.isoformat()),
            )
            self.connection.commit()

    def record_cycle(self, station_id: str, cycle_seconds: float, observed_at: datetime) -> None:
        with self._lock:
            self.connection.execute("INSERT INTO cycle_events(station_id, cycle_seconds, observed_at) VALUES (?, ?, ?)", (station_id, cycle_seconds, observed_at.isoformat()))
            self.connection.commit()

    def record_connector(self, endpoint_id: str, connected: bool, detail: str | None, observed_at: datetime) -> None:
        with self._lock:
            self.connection.execute("INSERT INTO connector_events(endpoint_id, connected, detail, observed_at) VALUES (?, ?, ?, ?)", (endpoint_id, int(connected), detail, observed_at.isoformat()))
            self.connection.commit()

    def record_counter(self, station_id: str, parts_counter: float, observed_at: datetime) -> None:
        with self._lock:
            self.connection.execute(
                "INSERT INTO counter_events(station_id, parts_counter, observed_at) VALUES (?, ?, ?)",
                (station_id, parts_counter, observed_at.isoformat()),
            )
            self.connection.commit()

    def record_signal(self, station_id: str, signal: str, old_value, new_value, observed_at: datetime) -> None:
        with self._lock:
            self.connection.execute(
                "INSERT INTO signal_events(station_id, signal, old_value, new_value, observed_at) VALUES (?, ?, ?, ?, ?)",
                (station_id, signal, json.dumps(old_value, default=str), json.dumps(new_value, default=str), observed_at.isoformat()),
            )
            self.connection.commit()

    def record_fault(self, station_id: str, alarm_id: str, category: str, description: str | None, active: bool, observed_at: datetime) -> None:
        with self._lock:
            self.connection.execute(
                "INSERT INTO fault_events(station_id, alarm_id, category, description, active, observed_at) VALUES (?, ?, ?, ?, ?, ?)",
                (station_id, alarm_id, category, description, int(active), observed_at.isoformat()),
            )
            self.connection.commit()

    @staticmethod
    def shift_at(observed_at: datetime, timezone_name: str) -> str:
        local = observed_at.astimezone(ZoneInfo(timezone_name))
        return "TM" if 6 <= local.hour < 14 else "TT" if 14 <= local.hour < 22 else "TN"

    def load_open_stoppages(self) -> list[dict]:
        with self._lock:
            return [dict(row) for row in self.connection.execute(
                "SELECT * FROM stoppage_events WHERE ended_at IS NULL ORDER BY started_at"
            ).fetchall()]

    def open_stoppage(
        self,
        *,
        line_id: str,
        station_id: str,
        reason: str,
        source_state: str,
        started_at: datetime,
        shift: str,
        classification: str,
        confidence: float,
        alarm_ids: list[str],
        alarm_code,
    ) -> dict:
        event_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        payload = {
            "id": event_id, "line_id": line_id, "station_id": station_id,
            "started_at": started_at.isoformat(), "ended_at": None, "duration_seconds": None,
            "reason": reason, "source_state": source_state, "shift": shift,
            "classification": classification, "confidence": confidence,
            "alarm_ids": json.dumps(alarm_ids), "alarm_code": None if alarm_code is None else str(alarm_code),
            "created_at": now, "updated_at": now,
        }
        with self._lock:
            existing = self.connection.execute(
                "SELECT * FROM stoppage_events WHERE station_id = ? AND ended_at IS NULL", (station_id,)
            ).fetchone()
            if existing:
                return dict(existing)
            self.connection.execute(
                """INSERT INTO stoppage_events(
                    id,line_id,station_id,started_at,ended_at,duration_seconds,reason,source_state,shift,
                    classification,confidence,alarm_ids,alarm_code,created_at,updated_at
                ) VALUES (
                    :id,:line_id,:station_id,:started_at,:ended_at,:duration_seconds,:reason,:source_state,:shift,
                    :classification,:confidence,:alarm_ids,:alarm_code,:created_at,:updated_at
                )""", payload,
            )
            self.connection.commit()
        return payload

    def close_stoppage(self, event_id: str, ended_at: datetime) -> None:
        with self._lock:
            row = self.connection.execute(
                "SELECT started_at FROM stoppage_events WHERE id = ? AND ended_at IS NULL", (event_id,)
            ).fetchone()
            if row is None:
                return
            started_at = datetime.fromisoformat(row["started_at"])
            duration = max(0.0, (ended_at - started_at).total_seconds())
            self.connection.execute(
                "UPDATE stoppage_events SET ended_at = ?, duration_seconds = ?, updated_at = ? WHERE id = ?",
                (ended_at.isoformat(), round(duration, 3), datetime.now(timezone.utc).isoformat(), event_id),
            )
            self.connection.commit()

    def stoppages(self, station_ids: list[str], start: datetime, end: datetime, now: datetime | None = None) -> list[dict]:
        if not station_ids:
            return []
        placeholders = ",".join("?" for _ in station_ids)
        effective_now = now or datetime.now(timezone.utc)
        with self._lock:
            rows = self.connection.execute(
                "SELECT * FROM stoppage_events "
                f"WHERE station_id IN ({placeholders}) AND started_at < ? AND (ended_at IS NULL OR ended_at > ?) "
                "ORDER BY started_at",
                (*station_ids, end.isoformat(), start.isoformat()),
            ).fetchall()
        result = []
        for row in rows:
            event = dict(row)
            started_at = datetime.fromisoformat(event["started_at"])
            finished_at = datetime.fromisoformat(event["ended_at"]) if event["ended_at"] else effective_now
            clipped_start, clipped_end = max(started_at, start), min(finished_at, end, effective_now)
            if clipped_end <= clipped_start:
                continue
            event["started_at"] = clipped_start.isoformat()
            event["ended_at"] = clipped_end.isoformat() if event["ended_at"] else None
            event["duration_seconds"] = round((clipped_end - clipped_start).total_seconds(), 3)
            event["alarm_ids"] = json.loads(event["alarm_ids"])
            event["open"] = row["ended_at"] is None
            result.append(event)
        return result

    def daily_history(self, station_id: str, day: date, timezone_name: str) -> dict:
        zone = ZoneInfo(timezone_name)
        start = datetime.combine(day, time.min, tzinfo=zone).astimezone(timezone.utc).isoformat()
        end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=zone).astimezone(timezone.utc).isoformat()

        def rows(query: str, parameters: tuple = (station_id, start, end)) -> list[dict]:
            cursor = self.connection.execute(query, parameters)
            return [dict(row) for row in cursor.fetchall()]

        with self._lock:
            # Include the last state before midnight: it is required to
            # calculate a stop that began on the previous shift/day.
            before = rows(
                "SELECT state, detail, observed_at FROM station_state_events "
                "WHERE station_id = ? AND observed_at < ? ORDER BY observed_at DESC LIMIT 1",
                (station_id, start),
            )
            states = rows("SELECT state, detail, observed_at FROM station_state_events WHERE station_id = ? AND observed_at >= ? AND observed_at < ? ORDER BY observed_at")
            if before:
                states.insert(0, before[0])
            return {
                "station_id": station_id,
                "date": day.isoformat(),
                "timezone": timezone_name,
                "day_start": start,
                "day_end": end,
                "cycles": rows("SELECT cycle_seconds, observed_at FROM cycle_events WHERE station_id = ? AND observed_at >= ? AND observed_at < ? ORDER BY observed_at"),
                "counters": rows("SELECT parts_counter, observed_at FROM counter_events WHERE station_id = ? AND observed_at >= ? AND observed_at < ? ORDER BY observed_at"),
                "states": states,
            }

    def stoppage_timeline(
        self,
        station_ids: list[str],
        last_day: date,
        days: int,
        timezone_name: str,
        micro_stop_seconds: int = 60,
    ) -> dict:
        """Return recorded non-running intervals over production days.

        A production day starts at 06:00 local time, matching the TM/TT/TN
        shifts used on the line.  State events are transitions, so the last
        event before the requested range is also loaded to correctly include a
        stop that began in the preceding production day.
        """
        if not station_ids:
            return {"events": [], "day_start": None, "day_end": None}

        zone = ZoneInfo(timezone_name)
        days = max(1, min(int(days), 14))
        first_day = last_day - timedelta(days=days - 1)
        day_start = datetime.combine(first_day, time(6), tzinfo=zone)
        day_end = datetime.combine(last_day + timedelta(days=1), time(6), tzinfo=zone)
        start_utc = day_start.astimezone(timezone.utc)
        end_utc = day_end.astimezone(timezone.utc)
        placeholders = ",".join("?" for _ in station_ids)

        with self._lock:
            rows = self.connection.execute(
                "SELECT station_id, state, detail, observed_at FROM station_state_events "
                f"WHERE station_id IN ({placeholders}) AND observed_at < ? ORDER BY station_id, observed_at",
                (*station_ids, end_utc.isoformat()),
            ).fetchall()

        per_station: dict[str, list[dict]] = {station_id: [] for station_id in station_ids}
        for row in rows:
            per_station[str(row["station_id"])].append(dict(row))

        durable = self.stoppages(station_ids, start_utc, end_utc)
        if durable:
            return {
                "timezone": timezone_name,
                "first_day": first_day.isoformat(),
                "last_day": last_day.isoformat(),
                "day_start": start_utc.isoformat(),
                "day_end": end_utc.isoformat(),
                "micro_stop_seconds": micro_stop_seconds,
                "events": [
                    {
                        "id": item["id"], "station_id": item["station_id"], "state": item["source_state"],
                        "type": "micro_stop" if item["duration_seconds"] <= micro_stop_seconds and item["reason"] == "WAITING" else item["reason"].lower(),
                        "reason": item["reason"], "detail": item["alarm_code"], "started_at": item["started_at"],
                        "ended_at": item["ended_at"], "duration_seconds": item["duration_seconds"], "shift": item["shift"],
                        "production_day": (
                            (datetime.fromisoformat(item["started_at"]).astimezone(zone) - timedelta(days=1)).date().isoformat()
                            if datetime.fromisoformat(item["started_at"]).astimezone(zone).hour < 6
                            else datetime.fromisoformat(item["started_at"]).astimezone(zone).date().isoformat()
                        ),
                        "classification": item["classification"], "confidence": item["confidence"], "open": item["open"],
                    }
                    for item in durable
                ],
            }

        events: list[dict] = []
        stopping_states = {"IDLE", "STOPPED", "FAULT", "MANUAL"}
        for station_id, transitions in per_station.items():
            for index, row in enumerate(transitions):
                started = datetime.fromisoformat(row["observed_at"])
                if started.tzinfo is None:
                    started = started.replace(tzinfo=timezone.utc)
                ended = (
                    datetime.fromisoformat(transitions[index + 1]["observed_at"])
                    if index + 1 < len(transitions)
                    else end_utc
                )
                if ended.tzinfo is None:
                    ended = ended.replace(tzinfo=timezone.utc)
                clipped_start, clipped_end = max(started, start_utc), min(ended, end_utc)
                if row["state"] not in stopping_states or clipped_end <= clipped_start:
                    continue
                duration_seconds = round((clipped_end - clipped_start).total_seconds(), 3)
                state = str(row["state"])
                if state in {"FAULT", "MANUAL"}:
                    stop_type = "repair_manual"
                elif duration_seconds <= micro_stop_seconds:
                    stop_type = "micro_stop"
                else:
                    stop_type = "stop_auto"
                local_start = clipped_start.astimezone(zone)
                shift = "TM" if 6 <= local_start.hour < 14 else "TT" if 14 <= local_start.hour < 22 else "TN"
                production_day = (local_start - timedelta(days=1)).date() if local_start.hour < 6 else local_start.date()
                events.append(
                    {
                        "station_id": station_id,
                        "state": state,
                        "type": stop_type,
                        "detail": row["detail"],
                        "started_at": clipped_start.isoformat(),
                        "ended_at": clipped_end.isoformat(),
                        "duration_seconds": duration_seconds,
                        "shift": shift,
                        "production_day": production_day.isoformat(),
                    }
                )
        events.sort(key=lambda item: (item["started_at"], item["station_id"]))
        return {
            "timezone": timezone_name,
            "first_day": first_day.isoformat(),
            "last_day": last_day.isoformat(),
            "day_start": start_utc.isoformat(),
            "day_end": end_utc.isoformat(),
            "micro_stop_seconds": micro_stop_seconds,
            "events": events,
        }

    def prune(self, retention_days: int) -> None:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat()
        with self._lock:
            for table in ("station_state_events", "cycle_events", "counter_events", "signal_events", "fault_events", "connector_events"):
                self.connection.execute(f"DELETE FROM {table} WHERE observed_at < ?", (cutoff,))
            self.connection.execute("DELETE FROM stoppage_events WHERE started_at < ? AND ended_at IS NOT NULL", (cutoff,))
            self.connection.execute("VACUUM")
            self.connection.commit()

    def close(self) -> None:
        with self._lock:
            self.connection.close()
