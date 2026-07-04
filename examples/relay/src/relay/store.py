"""SQLite storage for Relay: connection factory and schema.

One database file holds everything; every other module goes through
`connect()` and never opens sqlite3 directly, so the pragmas and the schema
exist in exactly one place.
"""
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  kind            TEXT    NOT NULL,
  payload         TEXT    NOT NULL DEFAULT '{}',
  status          TEXT    NOT NULL DEFAULT 'queued',
  priority        INTEGER NOT NULL DEFAULT 0,
  attempts        INTEGER NOT NULL DEFAULT 0,
  max_attempts    INTEGER NOT NULL DEFAULT 5,
  not_before      REAL    NOT NULL DEFAULT 0,
  lease_until     REAL,
  worker_id       TEXT,
  idempotency_key TEXT UNIQUE,
  last_error      TEXT,
  created_at      REAL    NOT NULL,
  updated_at      REAL    NOT NULL,
  CHECK (status IN ('queued', 'leased', 'done', 'dead'))
);
CREATE INDEX IF NOT EXISTS idx_jobs_claim
  ON jobs (status, not_before, priority, id);

CREATE TABLE IF NOT EXISTS schedules (
  name       TEXT    PRIMARY KEY,
  kind       TEXT    NOT NULL,
  payload    TEXT    NOT NULL DEFAULT '{}',
  interval_s REAL    NOT NULL,
  next_run   REAL    NOT NULL,
  enabled    INTEGER NOT NULL DEFAULT 1,
  CHECK (interval_s > 0)
);
"""


def connect(path):
    """Open (and if needed create) a Relay database.

    Autocommit mode: every statement commits on its own, which is what the
    single-statement atomic updates in queue.py rely on. WAL lets one writer
    and many readers coexist; busy_timeout makes concurrent writers wait
    instead of failing immediately.
    """
    conn = sqlite3.connect(path, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.executescript(SCHEMA)
    return conn
