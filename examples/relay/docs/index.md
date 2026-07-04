# Relay Documentation

Hub and source-of-truth registry for Relay - a persistent background job
queue on SQLite (standard library only). Read this first on every coding
task, then open the detail docs for the area you are touching.

## How knowledge is organized

Single package, so everything lives on one level in `docs/`. The two-level
model (product vs. area docs) only matters once this becomes a monorepo.

## How these docs are maintained

Reference voice, present tense, no changelog. Single source of truth: each
cross-cutting concept has one owner below; other docs link to it instead of
re-explaining it. Full rules in [`.claude/rules/style.md`](../.claude/rules/style.md).

## Source-of-truth registry

| Concept | Level | Owner doc | Code source |
|---------|-------|-----------|-------------|
| Job lifecycle (queued -> leased -> done / dead) | 1 | [queue.md](queue.md#job-lifecycle) | `src/relay/queue.py` |
| Leases & at-least-once delivery | 1 | [queue.md](queue.md#leases) | `src/relay/queue.py` |
| Idempotent enqueue | 1 | [queue.md](queue.md#idempotent-enqueue) | `src/relay/queue.py` |
| Retry policy & dead letter | 1 | [worker.md](worker.md) | `src/relay/worker.py` |
| Recurring schedules | 1 | [scheduler.md](scheduler.md) | `src/relay/scheduler.py` |
| Storage & schema | 1 | [storage.md](storage.md) | `src/relay/store.py` |

## Topics

| Topic | Doc |
|-------|-----|
| Queue core (enqueue, claim, settle, reap) | [queue.md](queue.md) |
| Worker & retry policy | [worker.md](worker.md) |
| Recurring schedules | [scheduler.md](scheduler.md) |
| Storage & schema | [storage.md](storage.md) |
| Command-line interface | [cli.md](cli.md) |
