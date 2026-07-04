# Read the docs before coding

The hub [`docs/index.md`](../../docs/index.md) (hub + source-of-truth registry)
is imported into context through `CLAUDE.md` - you already have it. For any task
that touches project code - writing, changing, refactoring, fixing bugs,
implementing features, or answering architecture questions - open the detail
docs the hub links for the area you are about to touch, **before** you write
any code. Never guess at something the docs cover.

Does not apply to: questions about tooling, git operations, configuring the
agent environment, or tasks that obviously do not touch project code.

If you are unsure whether a task is a coding task: ask, or read the docs anyway.

After a context compaction, re-open the detail docs for the area you are
working on - the compacted summary is not a substitute for them.

## Docs work stays inline

The whole loop lives inside the current task: read the relevant docs before
coding, update the owner doc in the same turn the code changes, done. Docs
maintenance is never split off into separate work:

- Do **not** suggest, queue, or schedule docs maintenance (audits, freshness
  sweeps, follow-up documentation) as background tasks or task suggestions -
  each started task runs in its own worktree and litters the repo.
- Do **not** run docs work in a separate worktree or isolated subagent; it
  happens in this session, in this working tree.
- Run the docs-audit skill only when the user explicitly asks for an audit
  (or as the final step of docs-setup) - never proactively.

If a docs gap is too large to close in the current turn, name it in the reply
and let the user decide - do not create follow-up work for it.
