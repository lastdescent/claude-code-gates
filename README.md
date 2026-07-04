# claude-code-gates

Deterministic quality gates for Claude Code. Two pillars, both hook-enforced:
the **docs loop** puts the project docs in the agent's context before it
changes code and keeps them updated in the same turn, and the **debt gates**
block the end of a turn until the side effects of a source change are
handled - tests run, call-sites visited, verify commands green. A strict
setup procedure ensures nothing in the docs is invented.

Built and tested for Claude Code. It uses Claude Code's native files - `CLAUDE.md`,
`.claude/rules/`, skills, and hooks. The structure is general, but the wiring is
Claude-specific and untested elsewhere; see [Scope](#scope).

## Background

I started coding with agents at the end of February 2026, on a small project, where
they kept dropping side effects - a change in one place, a related spot left stale.
That led to this structure, enforced with hooks; the agent's memory alone was not
reliable.

Since then I have put 500+ hours into Claude Code, and the difference is biggest on
much larger projects - the same kind of change goes through without those problems.
This is what I learned. Look through the repo, or try it if it is useful.

## How it works

Seven parts:

1. **Hub + registry** (`docs/index.md`). One entry point and one table mapping each
   cross-cutting concept to its single owner doc and the code behind it.
2. **Guaranteed read.** `CLAUDE.md` stays nearly empty - name, description, the two
   binding habits - and **imports the hub** (`@docs/index.md`), so the hub is in
   context in every session instead of hoping the agent reads it.
3. **Placement rule** (the swap test). Each fact has one location and one owner, so
   docs do not split into duplicated, conflicting copies.
4. **Reference-voice, grounded style.** Docs state current behavior, not its
   history, and record **observed behavior only** - unverified knowledge is a
   `TODO(verify)`, never plausible filler. An `Avoid` section records rejected
   approaches so they are not retried.
5. **Enforcement** (hooks). After a code change, a Stop hook blocks the turn until
   the affected docs are updated - and suggests the owner docs from the registry.
   A git-based net also catches edits made through shell commands (sed, codegen,
   scripts), not only the editing tools. A SessionStart hook cleans up stale
   session state and re-arms the system after context compaction.
6. **Debt gates** (hooks). A pre-edit guard makes the read-first rule
   deterministic - edits in a registry area are denied until its owner docs
   were read - fences the first edit in a new top-level directory, and
   protects lock/generated files. Changed source accrues debt: tests to run,
   call-sites of changed symbols to visit, verify commands to pass, debug
   leftovers to remove. A second Stop gate blocks the turn until it is
   resolved. Details in [docs/gates.md](docs/gates.md).
7. **Skills.** `docs-setup` installs the system into a target repo under a strict
   grounding contract (nothing invented - every fact from read code, read files,
   command output, or the user). `docs-audit` is a deterministic drift check:
   dead code paths, dead links, oversized docs, code newer than its doc,
   unregistered docs.

## What's in the box

```
CLAUDE.md                 near-empty template: name, description, hub import, two habits
docs/                     the toolkit's own hub + docs (dogfooding; not for copying)
templates/                the hub and feature-doc skeletons for target repos
.claude/rules/            what to read, how to write (incl. grounding), where knowledge lives
.claude/hooks/            seven hooks: the docs loop, the debt gates, session lifecycle
.claude/skills/           docs-setup (strict install) and docs-audit (drift check)
.claude/settings.json     wires the hooks into Claude Code
examples/relay/           a complete runnable example project with the system installed for real
```

## Requirements

- **Claude Code** - the system uses its native `CLAUDE.md` (with `@` imports),
  `.claude/rules/`, skills, and hooks (`SessionStart`, `PreToolUse`,
  `PostToolUse`, `Stop`, `SessionEnd`), wired in `.claude/settings.json`.
- **Python 3 on PATH** - the hooks and the audit are stdlib Python, no packages.
  On Windows, confirm `python --version` works and is not the Microsoft Store
  stub. Without Python the hooks cannot run and only the `CLAUDE.md` and rules
  instructions remain.
- **git** - the Bash-edit net, the session baseline, and the audit's freshness
  check use it. Without git those parts silently disable; Write/Edit tracking
  still works.

## Quickstart

**Easiest:** give Claude Code this repo and ask it to set the system up in your
project. The [`docs-setup` skill](.claude/skills/docs-setup/SKILL.md) gives it a
step-by-step procedure with a binding grounding contract: files are copied
verbatim, hook settings are derived from the actual repo layout, placeholders are
filled only from README/manifest or your answers, and the first docs are written
strictly from code the agent actually read - gaps become `TODO(verify)` markers,
never invented content. The run ends with the `docs-audit` check.

By hand, the same steps: copy `CLAUDE.md` and `.claude/` into your repo, set
`WATCH_DIRS`/`SOURCE_EXTENSIONS` in `.claude/hooks/docs-track.py` and
`.claude/hooks/debt-track.py` (identical in both) and the Python launcher in
`.claude/settings.json`, fill the two `CLAUDE.md` placeholders,
create `docs/index.md` from [`templates/index.md`](templates/index.md) and one
doc per area from [`templates/feature.md`](templates/feature.md), then run
`python .claude/skills/docs-audit/docs_audit.py` until clean.

From then on the agent has `docs/index.md` in context on every session, reads the
detail docs before coding, and updates the docs in the same turn; the Stop hook
blocks the turn until it does.

## Scope

This is distilled from a setup tested only on Claude Code. It has not been tested on
other agents (ChatGPT/Codex, Gemini, Cursor). The structure likely ports - `CLAUDE.md`
maps to `AGENTS.md`, and the rules and docs are plain Markdown - but that is
unverified, so this repo does not claim it.

## License

[MIT](LICENSE).
