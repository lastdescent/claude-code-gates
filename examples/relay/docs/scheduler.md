# Recurring schedules

Named schedules that enqueue a job every interval (`Scheduler` in
`src/relay/scheduler.py`). A schedule is a row, not a process: any process -
a worker loop, cron, the CLI - can call `tick()`, and several may do so
concurrently.

## Mechanism

1. `add(name, kind, payload, interval_s, start_at=None)` upserts the
   schedule; the first run is at `start_at` when given, otherwise one
   interval from now. Re-adding a name replaces it and re-enables it.
2. `tick(now)` selects enabled schedules with `next_run <= now` and, per due
   schedule, enqueues one job and advances `next_run`.
3. The enqueue carries `idempotency_key = "schedule:<name>@<next_run>"` - the
   run slot. A second process ticking the same slot enqueues nothing
   (deduplication is owned by [queue.md](queue.md#idempotent-enqueue)).
4. `next_run` advances past `now` in whole intervals
   (`next_run + periods * interval_s`), guarded by
   `WHERE name = ? AND next_run = ?` so concurrent ticks advance it once.

## Specifics

### No backfill

Missed slots collapse into one run: after downtime, `tick()` enqueues a
single job and jumps `next_run` into the future. A schedule that was due 8
intervals ago produces 1 job, not 8.

### Concurrent ticks

Two guarantees make `tick()` safe to run from several processes: the slot
idempotency key (at most one job per slot) and the optimistic `next_run`
guard (at most one advance per slot). Neither requires a lock or a leader.

### Enable / disable

`set_enabled(name, False)` keeps the row but excludes it from `tick()`;
re-enabling resumes from the stored `next_run` (which `tick()` then advances
past `now` without backfilling the downtime).

## Avoid

- Backfilling missed runs -> a flood of identical jobs after downtime;
  `next_run` jumps past `now` and the missed slots are skipped.
- Firing without the slot idempotency key -> two processes ticking the same
  due slot double-enqueue; the key makes the second enqueue a no-op
  (`tests/test_scheduler.py` exercises the refire).

## Files

| Role | Path |
|------|------|
| `Scheduler` | `src/relay/scheduler.py` |
| `schedules` table (owned by [storage.md](storage.md)) | `src/relay/store.py` |
| Backfill and refire tests | `tests/test_scheduler.py` |
