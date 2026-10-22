from __future__ import annotations

import sqlite3
import threading
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
