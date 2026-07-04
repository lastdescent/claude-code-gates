# Queue core

The job queue itself: enqueue, claim (lease), settle, reap. Lives in
`src/relay/queue.py` as `Queue` operating on the shared connection from
[storage.md](storage.md). Delivery is **at-least-once**: a job is only gone
once a worker acks it while still holding a live lease.

## Mechanism

1. `enqueue()` inserts a row with status `queued`; `not_before = now + delay_s`
   keeps delayed jobs invisible to claims until due.
2. `claim()` leases the next ready job (due `queued`, highest `priority`
   first, then FIFO by `id`) in **one** SQL statement - an `UPDATE` whose
   `WHERE id = (SELECT ...)` subquery picks the candidate under the same
   write lock, with `RETURNING *` handing back the row. Claiming increments
   `attempts`.
3. The worker settles the attempt: `ack()` -> `done`, `fail()` -> back to
   `queued` after `retry_in` seconds or `dead` when the attempts budget is
   spent, `bury()` -> `dead` immediately. Every settle statement requires a
   live lease (see [Leases](#leases)).
4. `release_expired()` requeues jobs whose lease ran out (crashed worker);
   exhausted jobs go to `dead` with `last_error = 'lease expired'`.
5. `requeue_dead()` moves dead jobs back to `queued` with a fresh attempts
   budget (`attempts = 0`).

## Specifics

### Job lifecycle

`status` is one of `queued | leased | done | dead` (enforced by a `CHECK`
constraint). Transitions: `queued -> leased` (claim), `leased -> done` (ack),
`leased -> queued` (fail with retries left, or lease expiry),
`leased -> dead` (fail on last attempt, bury, or lease expiry on last
attempt), `dead -> queued` (requeue_dead). `done` is terminal. `attempts`
counts deliveries and increments on claim, not on settle.

### Leases

A claim sets `worker_id` and `lease_until = now + lease_s` (wall clock, so
deadlines survive process restarts and are comparable across processes).
Every settle statement (`ack`, `fail`, `bury`, `extend_lease`) is a guarded
`UPDATE` matching `status = 'leased' AND worker_id = ? AND lease_until >= now`;
zero rows raises `StaleLeaseError`. A worker that outlives its lease
therefore cannot overwrite the job's new owner - its result is discarded and
the job runs again. `extend_lease()` is the heartbeat for long jobs.

### Idempotent enqueue

`idempotency_key` is a `UNIQUE` column; `enqueue()` inserts with
`ON CONFLICT (idempotency_key) DO NOTHING` and returns the existing job's id
when the key is already present. Jobs without a key are never deduplicated
(SQLite treats `NULL`s as distinct in unique indexes). The scheduler builds
on this for refire-safe ticks ([scheduler.md](scheduler.md)).

### Ordering

`ORDER BY priority DESC, id ASC` - higher priority first, FIFO within a
priority. `not_before` gates readiness: enqueue delay, retry backoff and
schedule slots all express themselves through it.

## Avoid

- Selecting a candidate first and leasing it in a second statement -> two
  workers select the same row before either updates it and both deliver the
  job (observed as 304 deliveries for 300 jobs in
  `tests/test_queue.py::TestConcurrentClaim`); claiming is a single
  `UPDATE ... WHERE id = (SELECT ...) RETURNING`.
- Settling without the `lease_until >= now` guard -> a worker that lost its
  lease overwrites the new owner's state; every settle checks status, worker
  and deadline in the `UPDATE` itself.
- Read-then-write transitions (read `attempts`, decide in Python, write) ->
  not atomic under autocommit; decisions like retry-vs-dead live in a `CASE`
  inside the one `UPDATE`.

## Files

| Role | Path |
|------|------|
| `Queue`, `Job`, `StaleLeaseError` | `src/relay/queue.py` |
| Schema and pragmas (owned by [storage.md](storage.md)) | `src/relay/store.py` |
| Lifecycle, lease and concurrency tests | `tests/test_queue.py` |
