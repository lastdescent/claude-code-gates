# Relay

A persistent background job queue on SQLite - standard library only, no
server, no dependencies. Producers enqueue jobs into a database file; workers
lease them with a visibility timeout and settle each attempt as done, retry
(exponential backoff), or dead. Named schedules enqueue recurring jobs.
Delivery is at-least-once with exclusive leases.

Requires Python 3.11+ (the claim statement uses `UPDATE ... RETURNING`,
SQLite 3.35+).

## Try it

```sh
# run the test suite
python -m unittest discover -s tests -t .

# use the CLI (module lives under src/)
export PYTHONPATH=src
python -m relay --db demo.db enqueue email --payload '{"to": "a@example.com"}'
python -m relay --db demo.db stats
python -m relay --db demo.db work --handlers my_handlers --max 1
```

`work` imports the named module and expects `HANDLERS = {kind: fn}`; each
handler receives the leased `Job`.

## Layout

```
src/relay/store.py      connection factory + schema (the only sqlite3 entry point)
src/relay/queue.py      enqueue, claim/lease, ack/fail/bury, reaping
src/relay/worker.py     handler registry, retry policy, worker loop
src/relay/scheduler.py  recurring jobs (interval schedules, no backfill)
src/relay/cli.py        argparse CLI over the three modules above
tests/                  unittest suite, deterministic (time injected via now=)
```

The docs in `docs/` are the source of truth for behavior; start at
[docs/index.md](docs/index.md).
