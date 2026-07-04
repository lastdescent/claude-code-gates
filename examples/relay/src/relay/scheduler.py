"""Recurring jobs: named schedules that enqueue a job every interval.

A schedule is a row, not a process - any process can call tick(). Firing is
idempotent (the enqueue carries an idempotency key derived from the run
slot), and missed runs collapse into the next one instead of backfilling.
"""
import json
import math
import time


class Scheduler:
    def __init__(self, conn, queue):
        self._conn = conn
        self._queue = queue

    def add(self, name, kind, payload=None, *, interval_s, start_at=None,
            now=None):
        """Create or replace a schedule. First run is at start_at when
        given, otherwise one interval from now."""
        now = time.time() if now is None else now
        next_run = start_at if start_at is not None else now + interval_s
        self._conn.execute(
            "INSERT INTO schedules (name, kind, payload, interval_s, next_run)"
            " VALUES (?, ?, ?, ?, ?)"
            " ON CONFLICT (name) DO UPDATE SET kind = excluded.kind,"
            "   payload = excluded.payload, interval_s = excluded.interval_s,"
            "   next_run = excluded.next_run, enabled = 1",
            (name, kind, json.dumps(payload or {}), interval_s, next_run))

    def remove(self, name):
        cur = self._conn.execute(
            "DELETE FROM schedules WHERE name = ?", (name,))
        return cur.rowcount == 1

    def set_enabled(self, name, enabled):
        cur = self._conn.execute(
            "UPDATE schedules SET enabled = ? WHERE name = ?",
            (1 if enabled else 0, name))
        return cur.rowcount == 1

    def list(self):
        return [dict(row) for row in self._conn.execute(
            "SELECT * FROM schedules ORDER BY name")]

    def tick(self, *, now=None):
        """Enqueue one job per due schedule and advance its next_run past
        now (missed slots are skipped, not backfilled). Returns the number
        of schedules fired.

        Safe to run from several processes: the enqueue deduplicates on
        'schedule:<name>@<slot>' and next_run is advanced with an optimistic
        guard, so a concurrent tick fires each slot at most once.
        """
        now = time.time() if now is None else now
        fired = 0
        due = self._conn.execute(
            "SELECT * FROM schedules WHERE enabled = 1 AND next_run <= ?",
            (now,)).fetchall()
        for row in due:
            self._queue.enqueue(
                row["kind"], json.loads(row["payload"]),
                idempotency_key=f"schedule:{row['name']}@{row['next_run']}",
                now=now)
            periods = math.floor((now - row["next_run"]) / row["interval_s"]) + 1
            self._conn.execute(
                "UPDATE schedules SET next_run = ?"
                " WHERE name = ? AND next_run = ?",
                (row["next_run"] + periods * row["interval_s"],
                 row["name"], row["next_run"]))
            fired += 1
        return fired
