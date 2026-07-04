# Storage & schema

One SQLite database file holds everything; `connect()` in
`src/relay/store.py` is the only place that opens it, so pragmas and schema
exist exactly once. Every other module receives the connection.

## Mechanism

`connect(path)` opens the file with `isolation_level=None` (autocommit),
sets `journal_mode=WAL` and `busy_timeout=5000`, installs `sqlite3.Row` as
row factory, and applies `SCHEMA` (idempotent `CREATE ... IF NOT EXISTS`),
creating the database on first use.

## Specifics

### jobs table

Columns: `id`, `kind`, `payload` (JSON text), `status` (constrained by
`CHECK` to `queued|leased|done|dead`), `priority`, `attempts`,
`max_attempts`, `not_before`, `lease_until`, `worker_id`,
`idempotency_key` (`UNIQUE`), `last_error`, `created_at`, `updated_at`.
All timestamps are wall-clock unix seconds (`REAL`). The claim path is
covered by `idx_jobs_claim` on `(status, not_before, priority, id)` -
exactly the filter and order used by `Queue.claim()`
([queue.md](queue.md)).

### schedules table

`name` (primary key), `kind`, `payload`, `interval_s` (`CHECK > 0`),
`next_run`, `enabled`. Owned behavior in [scheduler.md](scheduler.md).

### Autocommit contract

Every statement commits on its own. The queue's correctness relies on this:
each state transition is a single guarded `UPDATE`, atomic under SQLite's
write lock, with no multi-statement transaction to hold open. WAL allows
readers while a writer is active; `busy_timeout` makes concurrent writers
wait instead of raising immediately.

## Avoid

- Opening `sqlite3.connect` anywhere else -> misses the pragmas, the row
  factory and the schema; every module goes through `connect()`.
- In-memory databases in tests that use threads -> each connection would see
  its own empty database; the test fixture (`tests/base.py`) uses a file per
  test.

## Files

| Role | Path |
|------|------|
| `connect()`, `SCHEMA` | `src/relay/store.py` |
| Per-test database fixture | `tests/base.py` |
