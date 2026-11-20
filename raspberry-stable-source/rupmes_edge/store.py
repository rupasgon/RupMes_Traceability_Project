from __future__ import annotations

import sqlite3
import threading
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
            CREATE TABLE IF NOT EXISTS edge_configuration (id INTEGER PRIMARY KEY CHECK (id = 1), payload TEXT NOT NULL, updated_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS stoppage_events (id TEXT PRIMARY KEY, line_id TEXT NOT NULL, station_id TEXT NOT NULL, started_at TEXT NOT NULL, ended_at TEXT, duration_seconds REAL, reason TEXT NOT NULL, source_state TEXT NOT NULL, shift TEXT NOT NULL, confidence REAL NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS ix_stoppage_events_station_started ON stoppage_events(station_id, started_at);
            CREATE UNIQUE INDEX IF NOT EXISTS ux_stoppage_events_open_station ON stoppage_events(station_id) WHERE ended_at IS NULL;
            CREATE TABLE IF NOT EXISTS stoppage_sync_state (event_id TEXT PRIMARY KEY, synced_updated_at TEXT NOT NULL, synced_at TEXT NOT NULL);
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

    @staticmethod
    def shift_at(observed_at: datetime, timezone_name: str) -> str:
        hour = observed_at.astimezone(ZoneInfo(timezone_name)).hour
        return "TM" if 6 <= hour < 14 else "TT" if 14 <= hour < 22 else "TN"

    def load_open_stoppages(self) -> list[dict]:
        with self._lock:
            return [dict(row) for row in self.connection.execute("SELECT * FROM stoppage_events WHERE ended_at IS NULL").fetchall()]

    def pending_stoppage_sync(self, limit: int = 100) -> list[dict]:
        with self._lock:
            rows = self.connection.execute(
                "SELECT event.* FROM stoppage_events event LEFT JOIN stoppage_sync_state sync ON sync.event_id = event.id "
                "WHERE sync.event_id IS NULL OR sync.synced_updated_at < event.updated_at "
                "ORDER BY event.updated_at LIMIT ?", (limit,)
            ).fetchall()
            return [dict(row) for row in rows]

    def mark_stoppages_synced(self, events: list[dict]) -> None:
        with self._lock:
            now = datetime.now(timezone.utc).isoformat()
            self.connection.executemany(
                "INSERT INTO stoppage_sync_state(event_id,synced_updated_at,synced_at) VALUES (?,?,?) "
                "ON CONFLICT(event_id) DO UPDATE SET synced_updated_at=excluded.synced_updated_at,synced_at=excluded.synced_at",
                [(event["id"], event["updated_at"], now) for event in events],
            )
            self.connection.commit()

    def open_stoppage(self, line_id, station_id, reason, source_state, started_at, shift, confidence) -> dict:
        event = {"id": str(uuid.uuid4()), "line_id": line_id, "station_id": station_id, "started_at": started_at.isoformat(), "ended_at": None, "duration_seconds": None, "reason": reason, "source_state": source_state, "shift": shift, "confidence": confidence, "created_at": datetime.now(timezone.utc).isoformat(), "updated_at": datetime.now(timezone.utc).isoformat()}
        with self._lock:
            existing = self.connection.execute("SELECT * FROM stoppage_events WHERE station_id = ? AND ended_at IS NULL", (station_id,)).fetchone()
            if existing:
                return dict(existing)
            self.connection.execute("INSERT INTO stoppage_events(id,line_id,station_id,started_at,ended_at,duration_seconds,reason,source_state,shift,confidence,created_at,updated_at) VALUES (:id,:line_id,:station_id,:started_at,:ended_at,:duration_seconds,:reason,:source_state,:shift,:confidence,:created_at,:updated_at)", event)
            self.connection.commit()
        return event

    def close_stoppage(self, event_id: str, ended_at: datetime) -> None:
        with self._lock:
            row = self.connection.execute("SELECT started_at FROM stoppage_events WHERE id = ? AND ended_at IS NULL", (event_id,)).fetchone()
            if row:
                seconds = max(0, (ended_at - datetime.fromisoformat(row["started_at"])).total_seconds())
                self.connection.execute("UPDATE stoppage_events SET ended_at=?, duration_seconds=?, updated_at=? WHERE id=?", (ended_at.isoformat(), round(seconds, 3), datetime.now(timezone.utc).isoformat(), event_id))
                self.connection.commit()

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
        """Return durable, classified stoppage events for the requested window.

        Events are recorded by ``StoppageTracker`` when they start and finish.
        Do not reconstruct them from arbitrary station-state samples here: that
        caused an unfinished state to be projected to the end of the selected
        day and made the analysis misleading after a restart.
        """
        if not station_ids:
            return {"events": [], "day_start": None, "day_end": None}
        zone = ZoneInfo(timezone_name)
        days = max(1, min(int(days), 14))
        first_day = last_day - timedelta(days=days - 1)
        day_start = datetime.combine(first_day, time(6), tzinfo=zone)
        day_end = datetime.combine(last_day + timedelta(days=1), time(6), tzinfo=zone)
        start_utc, end_utc = day_start.astimezone(timezone.utc), day_end.astimezone(timezone.utc)
        placeholders = ",".join("?" for _ in station_ids)
        with self._lock:
            rows = self.connection.execute(
                "SELECT id, station_id, started_at, ended_at, duration_seconds, reason, "
                "source_state, shift, confidence "
                "FROM stoppage_events "
                f"WHERE station_id IN ({placeholders}) AND started_at < ? "
                "AND (ended_at IS NULL OR ended_at > ?) "
                "ORDER BY started_at, station_id",
                (*station_ids, end_utc.isoformat(), start_utc.isoformat()),
            ).fetchall()

        events: list[dict] = []
        now_utc = datetime.now(timezone.utc)
        for row in rows:
            item = dict(row)
            started = datetime.fromisoformat(item["started_at"])
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            finished = datetime.fromisoformat(item["ended_at"]) if item["ended_at"] else now_utc
            if finished.tzinfo is None:
                finished = finished.replace(tzinfo=timezone.utc)
            interval_start, interval_end = max(started, start_utc), min(finished, end_utc, now_utc)
            if interval_end <= interval_start:
                continue
            seconds = round((interval_end - interval_start).total_seconds(), 3)
            reason = str(item["reason"])
            stop_type = "micro_stop" if reason in {"STOPPED", "WAITING"} and seconds <= micro_stop_seconds else reason.lower()
            local_start = interval_start.astimezone(zone)
            events.append({
                "id": item["id"], "station_id": item["station_id"], "reason": reason,
                "source_state": item["source_state"], "type": stop_type,
                "started_at": interval_start.isoformat(), "ended_at": interval_end.isoformat(),
                "duration_seconds": seconds, "open": item["ended_at"] is None,
                "shift": item["shift"], "confidence": item["confidence"],
                "production_day": ((local_start - timedelta(days=1)).date() if local_start.hour < 6 else local_start.date()).isoformat(),
            })
        events.sort(key=lambda item: (item["started_at"], item["station_id"]))
        return {"timezone": timezone_name, "first_day": first_day.isoformat(), "last_day": last_day.isoformat(), "day_start": start_utc.isoformat(), "day_end": end_utc.isoformat(), "micro_stop_seconds": micro_stop_seconds, "events": events}

    def prune(self, retention_days: int) -> None:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat()
        with self._lock:
            for table in ("station_state_events", "cycle_events", "counter_events", "connector_events"):
                self.connection.execute(f"DELETE FROM {table} WHERE observed_at < ?", (cutoff,))
            self.connection.execute("VACUUM")
            self.connection.commit()

    def close(self) -> None:
        with self._lock:
            self.connection.close()
