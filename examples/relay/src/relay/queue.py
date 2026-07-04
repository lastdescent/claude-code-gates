"""Job queue core: enqueue, claim (lease), ack/fail/bury, reaping.

Delivery contract is at-least-once: a job is only gone once a worker acks it
while still holding a live lease. Every state transition is a single guarded
UPDATE, so two workers on the same database can never both own a job.
"""
import json
import time
from dataclasses import dataclass

VALID_STATUSES = ("queued", "leased", "done", "dead")


class StaleLeaseError(RuntimeError):
    """The caller no longer holds the lease it is trying to act on."""


@dataclass(frozen=True)
class Job:
    id: int
    kind: str
    payload: dict
    status: str
    priority: int
    attempts: int
    max_attempts: int
    not_before: float
    lease_until: float | None
    worker_id: str | None
    idempotency_key: str | None
    last_error: str | None
    created_at: float
    updated_at: float

    @classmethod
    def from_row(cls, row):
        return cls(
            id=row["id"], kind=row["kind"],
            payload=json.loads(row["payload"]), status=row["status"],
            priority=row["priority"], attempts=row["attempts"],
            max_attempts=row["max_attempts"], not_before=row["not_before"],
            lease_until=row["lease_until"], worker_id=row["worker_id"],
            idempotency_key=row["idempotency_key"],
            last_error=row["last_error"],
            created_at=row["created_at"], updated_at=row["updated_at"],
        )


class Queue:
    def __init__(self, conn):
        self._conn = conn

    # -- producing ---------------------------------------------------------

    def enqueue(self, kind, payload=None, *, priority=0, max_attempts=5,
                delay_s=0.0, idempotency_key=None, now=None):
        """Add a job; returns its id.

        With an idempotency_key, re-enqueueing the same key returns the
        existing job's id instead of inserting a duplicate.
        """
        now = time.time() if now is None else now
        cur = self._conn.execute(
            "INSERT INTO jobs (kind, payload, priority, max_attempts,"
            "                  not_before, idempotency_key, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT (idempotency_key) DO NOTHING",
            (kind, json.dumps(payload or {}), priority, max_attempts,
             now + delay_s, idempotency_key, now, now))
        if cur.rowcount == 1:
            return cur.lastrowid
        row = self._conn.execute(
            "SELECT id FROM jobs WHERE idempotency_key = ?",
            (idempotency_key,)).fetchone()
        return row["id"]

    # -- consuming ---------------------------------------------------------

    def claim(self, worker_id, *, kinds=None, lease_s=60.0, now=None):
        """Lease the next ready job for worker_id; None when nothing is ready.

        Ready means status 'queued' and not_before due; highest priority
        first, then FIFO. Claiming counts as a delivery attempt.

        Selection and lease are ONE statement: SQLite runs the subquery and
        the update under the same write lock, so concurrent claimers can
        never lease the same job.
        """
        now = time.time() if now is None else now
        kind_filter, params = "", []
        if kinds is not None:
            if not kinds:
                return None
            kind_filter = (" AND kind IN (%s)" % ",".join("?" * len(kinds)))
            params = list(kinds)
        row = self._conn.execute(
            "UPDATE jobs SET status = 'leased', attempts = attempts + 1,"
            "                worker_id = ?, lease_until = ?, updated_at = ?"
            " WHERE id = (SELECT id FROM jobs"
            "              WHERE status = 'queued' AND not_before <= ?"
            + kind_filter +
            "              ORDER BY priority DESC, id ASC LIMIT 1)"
            " RETURNING *",
            [worker_id, now + lease_s, now, now] + params).fetchone()
        return None if row is None else Job.from_row(row)

    def ack(self, job_id, worker_id, *, now=None):
        """Mark a job done. Requires a live lease held by worker_id."""
        now = time.time() if now is None else now
        cur = self._conn.execute(
            "UPDATE jobs SET status = 'done', lease_until = NULL,"
            "                updated_at = ?"
            " WHERE id = ? AND status = 'leased' AND worker_id = ?"
            "   AND lease_until >= ?",
            (now, job_id, worker_id, now))
        if cur.rowcount == 0:
            raise StaleLeaseError(f"job {job_id}: lease not held by {worker_id!r}")

    def fail(self, job_id, worker_id, *, error, retry_in=0.0, now=None):
        """Record a failed attempt: back to 'queued' after retry_in seconds,
        or 'dead' when the attempts budget is spent. Requires a live lease."""
        now = time.time() if now is None else now
        cur = self._conn.execute(
            "UPDATE jobs SET"
            "  status = CASE WHEN attempts >= max_attempts"
            "                THEN 'dead' ELSE 'queued' END,"
            "  not_before = ?, last_error = ?,"
            "  lease_until = NULL, worker_id = NULL, updated_at = ?"
            " WHERE id = ? AND status = 'leased' AND worker_id = ?"
            "   AND lease_until >= ?",
            (now + retry_in, error, now, job_id, worker_id, now))
        if cur.rowcount == 0:
            raise StaleLeaseError(f"job {job_id}: lease not held by {worker_id!r}")

    def bury(self, job_id, worker_id, *, error, now=None):
        """Move a job straight to 'dead' (permanent failure), skipping
        remaining retries. Requires a live lease."""
        now = time.time() if now is None else now
        cur = self._conn.execute(
            "UPDATE jobs SET status = 'dead', last_error = ?,"
            "                lease_until = NULL, worker_id = NULL, updated_at = ?"
            " WHERE id = ? AND status = 'leased' AND worker_id = ?"
            "   AND lease_until >= ?",
            (error, now, job_id, worker_id, now))
        if cur.rowcount == 0:
            raise StaleLeaseError(f"job {job_id}: lease not held by {worker_id!r}")

    def extend_lease(self, job_id, worker_id, *, lease_s=60.0, now=None):
        """Heartbeat: push the lease deadline out. Requires a live lease."""
        now = time.time() if now is None else now
        cur = self._conn.execute(
            "UPDATE jobs SET lease_until = ?, updated_at = ?"
            " WHERE id = ? AND status = 'leased' AND worker_id = ?"
            "   AND lease_until >= ?",
            (now + lease_s, now, job_id, worker_id, now))
        if cur.rowcount == 0:
            raise StaleLeaseError(f"job {job_id}: lease not held by {worker_id!r}")

    # -- maintenance -------------------------------------------------------

    def release_expired(self, *, now=None):
        """Requeue jobs whose lease ran out (crashed or stuck worker); jobs
        with no attempts left go to 'dead'. Returns how many were touched."""
        now = time.time() if now is None else now
        cur = self._conn.execute(
            "UPDATE jobs SET"
            "  status = CASE WHEN attempts >= max_attempts"
            "                THEN 'dead' ELSE 'queued' END,"
            "  last_error = CASE WHEN attempts >= max_attempts"
            "                    THEN 'lease expired' ELSE last_error END,"
            "  lease_until = NULL, worker_id = NULL, updated_at = ?"
            " WHERE status = 'leased' AND lease_until < ?",
            (now, now))
        return cur.rowcount

    def requeue_dead(self, job_id=None, *, now=None):
        """Give dead jobs a fresh attempts budget and requeue them.
        With job_id, only that job; otherwise all dead jobs. Returns count."""
        now = time.time() if now is None else now
        where, params = "status = 'dead'", [now, now]
        if job_id is not None:
            where += " AND id = ?"
            params.append(job_id)
        cur = self._conn.execute(
            "UPDATE jobs SET status = 'queued', attempts = 0,"
            "                not_before = ?, updated_at = ?"
            f" WHERE {where}", params)
        return cur.rowcount

    # -- introspection -----------------------------------------------------

    def get(self, job_id):
        row = self._conn.execute(
            "SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return None if row is None else Job.from_row(row)

    def stats(self, *, now=None):
        """Counts per status, plus 'ready' (queued and due now)."""
        now = time.time() if now is None else now
        counts = {s: 0 for s in VALID_STATUSES}
        for row in self._conn.execute(
                "SELECT status, COUNT(*) AS n FROM jobs GROUP BY status"):
            counts[row["status"]] = row["n"]
        ready = self._conn.execute(
            "SELECT COUNT(*) AS n FROM jobs"
            " WHERE status = 'queued' AND not_before <= ?", (now,)).fetchone()
        counts["ready"] = ready["n"]
        return counts
