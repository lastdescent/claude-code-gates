# Example: Relay

[`relay/`](relay/) is a complete, runnable example of what this toolkit
produces: a real project with the docs system installed **for real** - the
files here are the unmodified output of that run, not hand-written samples.

## What Relay is

A persistent background job queue on SQLite, standard library only: exclusive
leases with visibility timeouts, retries with exponential backoff, a dead
letter state, recurring schedules, a CLI. Small enough to read in one
sitting, complex enough to have real cross-cutting concepts - the
source-of-truth registry in [`relay/docs/index.md`](relay/docs/index.md) has
six entries across five detail docs.

```sh
cd examples/relay
python -m unittest discover -s tests -t .   # 40 tests
```

## How this example was produced

1. The project was developed first, test suite and CLI included. The `Avoid`
   sections in its docs record constraints that were actually observed
   during that development - e.g. the claim race (naive SELECT-then-UPDATE
   claiming delivered 304 of 300 jobs to the four concurrent test workers)
   is real, reproduced by `tests/test_queue.py::TestConcurrentClaim` before
   the claim became a single atomic `UPDATE ... RETURNING`.
2. Then the [docs-setup skill](../.claude/skills/docs-setup/SKILL.md) was
   followed step by step in that repo: toolkit files copied verbatim, hooks
   configured from observed facts, `CLAUDE.md` placeholders filled from the
   project README, the docs written strictly from code read in that session.
3. `docs_audit.py` ran clean (6 docs), the test suite green, before the
   files were copied here unchanged.

## What the setup configured, and from which observation

| Setting | Value | Observation |
|---------|-------|-------------|
| `WATCH_DIRS` (both trackers) | `("src",)` | `git ls-files`: all source under `src/` |
| `SOURCE_EXTENSIONS` | defaults | only `.py` occurs; defaults already cover it |
| `TEST_COMMAND_PATTERNS` | defaults + `"unittest"` | the repo runs tests via `python -m unittest discover -s tests -t .` |
| `REQUIRE_TESTS` / `TEST_SUGGESTION` | `True` / that command | working suite observed (40 tests, green) |
| `VERIFY_COMMANDS` | `("python -m compileall -q src",)` | ran once during setup, exit 0; the full suite deliberately stays out of verify |
| Python launcher | `python` | `python --version` prints a real version on this machine |

## What is deliberately not duplicated here

The example ships without its `.claude/` directory: those files are verbatim
copies of this toolkit's `CLAUDE.md` companions (rules, seven hooks,
settings, docs-audit skill), differing only in the configuration values in
the table above. Duplicating them under `examples/` would let them drift
from the real ones one directory up. `relay/CLAUDE.md` and
`relay/.gitignore` are included - they are per-project artifacts, not
copies.

The toolkit's own audit skips `examples/` (see `SKIP_DIRS` in
[`docs_audit.py`](../.claude/skills/docs-audit/docs_audit.py)); the
example's docs were audited in the repo they were written in.
