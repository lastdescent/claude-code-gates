# How docs are written

Docs in this project describe the **current state** in present-tense reference
voice - what is true now, and the standing constraints that keep it true. They
are not a changelog: they do not narrate how the present code came to be.

Recording a rejected alternative is **not** a changelog entry. The `## Avoid`
section captures approaches that do not work so they are not tried again - that
is part of the current state, a standing constraint, written in present tense
and without reference to when or by whom an approach was tried.

## Grounding

Docs record **observed behavior only**. Every statement must be traceable to
code read (or behavior verified) in the session that writes it - if you did not
read it, you do not write it. Unverified knowledge is written as
`TODO(verify): <question>` or left out; it is never stated as fact. Docs do not
describe intent, plans, or roadmap ("will", "planned", "should eventually") -
only what the code does now. A short true doc beats a complete invented one.

## Placement

Two levels, governed by the **swap test** (defined in
[`docs/index.md`](../../docs/index.md)): product-wide knowledge in `docs/`,
area-specific knowledge in `<area>/docs/`. Most projects use only `docs/`. Do not
duplicate the level model here - the hub owns it.

## Single source of truth

Every cross-cutting concept has exactly **one** owner doc, listed in the registry
in [`docs/index.md`](../../docs/index.md). The procedure on every change:

- Before documenting a cross-cutting concept: check the registry, edit **only the
  owner doc**.
- Other docs link to the owner section (`[...](owner.md#anchor)`) and do **not**
  duplicate the text - at most a one-line pointer for context.
- When a cross-cutting concept changes in the code, the **owner doc** is updated,
  not the docs that link to it.
- A new cross-cutting concept (a term that appears in >= 2 docs) -> add it to the
  registry and assign an owner.

**One fact, one owner - not one topic, one owner.** When a doc touches a topic
another level or doc owns (e.g. a feature doc whose legal side is owned by a
compliance doc), it describes only its own part and **links** the rest. Every
single fact then has exactly one owner, even in grey-area topics.

## Shape of a doc

Every feature doc has these sections, in order. The skeleton is
[`templates/feature.md`](../../templates/feature.md); the example docs follow it.

- **Title + intro** - the feature name, then one or two sentences on what it is and
  its goal. Note any naming split (UI name vs code name) up front.
- `## Mechanism` - how it works. A numbered list when the flow is sequential, prose
  otherwise. Reference code with backticked paths and symbol names.
- `## Specifics` - data shapes, states, and the invariants a change must hold. One
  `###` per aspect.
- `## Avoid` - what not to do, and alternatives that are rejected, as
  `approach -> why it does not work` (present tense - a standing constraint, not
  a record of when it was tried).
- `## Files` - a role -> path table of where the feature lives. Move a path when the
  code moves.

## Conventions

- **File names:** kebab-case, named by topic (`auth.md`, `billing.md`, `sync.md`).
- **Links between docs:** relative (`../docs/index.md`), never absolute.
- **No dates.** Docs describe the current state, so they carry no dates at all -
  no `YYYY-MM-DD`, no "as of Month Year", no "currently" or "last week". Anything
  that is only true until a known point belongs in the commit, not the doc.
- **One concept per doc.** If a doc grows two unrelated halves, split it and
  register both.
- **Size budget.** A doc that grows past ~200 lines is split by concept and
  both halves registered in the hub - the docs are read at the start of every
  coding session, so their size is a recurring context cost.
