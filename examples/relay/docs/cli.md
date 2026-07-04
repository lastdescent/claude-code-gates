# Command-line interface

`relay <command>` against a database file (`--db`, default `relay.db`).
Implemented in `src/relay/cli.py`; `python -m relay` enters through
`src/relay/__main__.py`. The CLI parses arguments, calls exactly one API
function, prints the result - behavior lives in the library modules.

## Mechanism

| Command | Calls |
|---------|-------|
| `enqueue KIND [--payload JSON] [--priority N] [--max-attempts N] [--delay S] [--key K]` | `Queue.enqueue`, prints the job id |
| `stats` | `Queue.stats`, one `status count` line each |
| `reap` | `Queue.release_expired`, prints the count |
| `dead list` / `dead requeue [ID]` | reads dead jobs / `Queue.requeue_dead` |
| `schedule add NAME KIND --interval S [--payload JSON]` / `list` / `rm NAME` / `tick` | `Scheduler` methods |
| `work --handlers MODULE [--max N] [--poll S] [--lease S]` | builds a `Worker`, registers the module's handlers, `Worker.run` |

## Specifics

### Handler modules

`work --handlers MODULE` imports `MODULE` with `importlib` and expects
`HANDLERS = {kind: fn}` at module level; each fn receives the leased `Job`
(contract in [worker.md](worker.md#handler-contract)). The module must be
importable from the working directory (`python -m` puts the cwd on the
path).

### Exit codes

`main(argv)` returns the exit code: `0` on success, `1` when
`schedule rm` names an unknown schedule. Errors from bad input (invalid
JSON payload, unknown command) surface as exceptions/argparse errors.

## Avoid

- Business logic in `cli.py` -> unreachable for library users; the CLI stays
  a thin shell where each command maps to one call in
  `src/relay/queue.py` / `src/relay/scheduler.py` / `src/relay/worker.py`.

## Files

| Role | Path |
|------|------|
| Argument parsing and dispatch | `src/relay/cli.py` |
| `python -m relay` entry point | `src/relay/__main__.py` |
| CLI tests (in-process `main()` calls) | `tests/test_cli.py` |
