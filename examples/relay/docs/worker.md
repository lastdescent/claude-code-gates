# Worker & retry policy

`Worker` (`src/relay/worker.py`) claims jobs it has handlers for, runs them,
and maps the outcome to a queue transition. This doc owns the **retry policy
and dead-letter** concept; the transition mechanics belong to
[queue.md](queue.md#job-lifecycle).

## Mechanism

1. Handlers are registered per job kind - `worker.register(kind, fn)` or the
   `@worker.handler(kind)` decorator.
2. `run_once()` claims with `kinds=tuple(self._handlers)`, so only kinds this
   worker can handle are taken; other jobs stay `queued` for a worker that
   knows them.
3. Outcome mapping: handler returns -> `ack`; raises `PermanentError` ->
   `bury` (dead, no retries); raises anything else -> `fail` with
   `retry_in = backoff(job.attempts)`.
4. A `StaleLeaseError` from any settle means the lease expired mid-run and
   the job has a new owner: the result is discarded, nothing is written
   (see [queue.md](queue.md#leases)).
5. `run()` is the blocking loop: calls `release_expired()` every
   `reap_every` iterations, sleeps `poll_s` when the queue is empty, stops
   after `max_jobs`.

## Specifics

### Retry policy

`backoff(attempt, base=1.0, factor=2.0, cap=300.0)` returns
`min(cap, base * factor ** (attempt - 1))` seconds - 1s, 2s, 4s, ... capped
at 5 minutes. `attempt` is `Job.attempts`, which counts deliveries
(incremented on claim), so the first failure waits `base` seconds. Per-worker
tuning via `Worker(backoff_base=..., backoff_cap=...)`.

### Dead letter

Jobs land in `dead` three ways: `fail()` on the last attempt, `bury()` on
`PermanentError`, or lease expiry with no attempts left. `last_error` records
the reason. `requeue_dead()` (also `relay dead requeue`) returns them to
`queued` with `attempts = 0`.

### Handler contract

A handler receives the leased `Job` (frozen dataclass; `payload` is the
decoded dict). Raising `PermanentError` marks the input unprocessable -
retries would fail identically. Any other exception is treated as transient.

## Avoid

- Claiming kinds without a registered handler -> burns delivery attempts on
  jobs some other worker could process; the claim filters on registered
  kinds.
- Treating `StaleLeaseError` as a job failure -> the job already belongs to
  another worker; failing it would corrupt that owner's state. The result is
  discarded instead.

## Files

| Role | Path |
|------|------|
| `Worker`, `PermanentError`, `backoff` | `src/relay/worker.py` |
| Settle transitions (owned by [queue.md](queue.md)) | `src/relay/queue.py` |
| Outcome and backoff tests | `tests/test_worker.py` |
