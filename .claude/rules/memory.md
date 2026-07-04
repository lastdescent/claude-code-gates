# Knowledge lives in the repo, not in private memory

Durable project knowledge - architecture decisions, conventions, how features
work, the current state of things - is versioned in the repo, not stored in the
agent's local or private memory. Product-wide knowledge goes to `docs/`,
area-specific knowledge to `<area>/docs/` (the level model is in
[`docs/index.md`](../../docs/index.md)).

When you learn something durable about the project: create or extend the right doc
on the right level and register it in the hub `docs/index.md` - do **not** create a
private memory entry for it.

Why: docs in the repo are shared, reviewable, and survive across sessions, tools,
and people. Knowledge in one agent's private memory is invisible to everyone else
and not versioned.
