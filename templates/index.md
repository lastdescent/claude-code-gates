# {{PROJECT_NAME}} Documentation

This is the hub for the whole project's documentation and the **single** place
that decides where knowledge lives. It is imported into context through
`CLAUDE.md`; on every coding task, open the detail docs linked below for the
area you are working on.

## How knowledge is organized

<!--
  Most projects need only ONE level: a flat docs/ folder (the "Topics" table
  below). Keep it that way until a monorepo forces a split. The two-level model
  and the swap test are written down here so the rule exists once; delete the
  parts you do not use.
-->

Docs sit on one or two levels so nothing is maintained twice:

| Level | Location | Holds |
|-------|----------|-------|
| **1 - Product** | `docs/` (here) | Anything true about the product regardless of how it is built: conventions, architecture that spans areas, product-wide concepts. |
| **2 - Area** | `<area>/docs/` (e.g. `apps/web/docs/`) | The *how* of one area: its features and internal implementation. Only used in monorepos / multi-area repos. |

**The swap test (which level?):** *Would this doc still be needed if you replaced
this area with a completely different one?* **Yes -> Level 1 (`docs/`). No -> Level 2
(`<area>/docs/`).** A single-package project only ever uses Level 1.

## How these docs are maintained

The full rules are in [`.claude/rules/style.md`](../.claude/rules/style.md). In short:

- **Reference voice, not a changelog.** Docs describe the current state in the
  present tense. The *why* of a single fix belongs in the commit, not the prose.
- **Grounded.** Docs record observed behavior only - nothing is written that was
  not verified in the code; gaps are `TODO(verify)`, never plausible filler.
- **Single source of truth.** Every cross-cutting concept has exactly one owner
  doc (the registry below). Other docs link to it; they never re-explain it.
- **One fact, one owner.** When a doc touches a concept another doc owns, it
  states only its own part and links the rest.
- **Hard-won lessons survive** - compressed, under a `## Avoid` section, as
  `approach -> why it failed` bullets, so nothing is rebuilt that already failed.
- **Files table.** Every feature doc ends with a `## Files` table (role -> path) -
  the jump from *what it does* to *where to change it*.

## Source-of-truth registry

Cross-cutting concepts - anything that shows up in two or more docs. Before
documenting or changing one of these, edit **only the owner doc**; everything else
links to it.

| Concept | Level | Owner doc | Code source |
|---------|-------|-----------|-------------|
<!-- Example row - replace with your project's real concepts:
| Authentication & sessions | 1 | [auth.md](auth.md) | `src/auth/` |
-->
| _{{concept}}_ | _1_ | _[{{doc}}.md]({{doc}}.md)_ | _`{{path}}`_ |

## Topics

<!-- One row per detail doc. This is the table of contents. -->

| Topic | Doc |
|-------|-----|
| _{{topic}}_ | _[{{doc}}.md]({{doc}}.md)_ |
