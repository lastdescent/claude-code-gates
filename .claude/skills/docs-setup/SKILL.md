---
name: docs-setup
description: Install the claude-code-gates system into a target repository and write the initial docs strictly from code that was actually read. Use when asked to set up this docs system in a project. Also usable as a written procedure when this repo was cloned as a reference.
---

# Set up the docs system in a target repo

Install the toolkit's files into a target repository, configure the hooks from
observed facts, and write the first docs. Follow the steps in order and do not
skip the verification at the end.

## Grounding contract - binding for every step

**Nothing is invented.** Every fact that ends up in the target's `CLAUDE.md` or
`docs/` must come from one of exactly four sources:

1. code you read in this session,
2. a file you read (README, package manifest, config),
3. the output of a command you ran,
4. an explicit answer from the user.

If a placeholder or doc section cannot be filled from those sources, **ask the
user** - do not guess, do not write plausible filler. Further:

- Copied files are copied **verbatim**. Do not "improve", reword, restructure,
  or reformat them.
- Never document intent or roadmap - only current behavior you verified.
- Every path you write into a doc must be verified to exist (Glob or `ls`)
  before the doc is saved.
- A short true doc beats a complete invented one. Gaps are marked
  `TODO(verify): <question>`, never papered over.

## Steps

### 1. Copy the files verbatim

From this toolkit into the target repo root:

| Source | Target | Notes |
|--------|--------|-------|
| `CLAUDE.md` | `CLAUDE.md` | placeholders filled in step 3 |
| `.claude/rules/` (all three files) | `.claude/rules/` | verbatim |
| `.claude/hooks/docs-track.py`, `docs-stop-gate.py`, `docs-session-start.py`, `docs-session-end.py` | `.claude/hooks/` | configured in step 2 |
| `.claude/hooks/edit-guard.py`, `debt-track.py`, `debt-stop-gate.py` | `.claude/hooks/` | configured in step 2 |
| `.claude/settings.json` | `.claude/settings.json` | **merge** the hook arrays if the file already exists - never overwrite unrelated settings |
| `.claude/skills/docs-audit/` | `.claude/skills/docs-audit/` | so the target can audit itself |
| `templates/index.md` | basis for the target's `docs/index.md` | step 4 |
| `templates/feature.md` | basis for each detail doc | step 4 |
| `.gitignore` entries for `.docs-*` / `.debt-*` / `.gate-log.jsonl*` under `.claude/hooks/` | target `.gitignore` | append if missing |

Do **not** copy the toolkit's `docs/` - it documents the toolkit itself.

### 2. Configure the hooks from observed facts

- **`WATCH_DIRS`** in `docs-track.py`: run `git ls-files` in the target and
  observe which top-level directories actually contain source files. Set
  `WATCH_DIRS` to those directories. If source lives at the repo root or the
  layout is ambiguous, ask the user - do not guess.
- **`SOURCE_EXTENSIONS`**: keep the defaults, add extensions that actually
  occur in the target's source (visible in `git ls-files`), and only remove
  entries the user confirms are irrelevant.
- **Python launcher**: run `python --version` and `python3 --version`. Use the
  one that prints a real version in `.claude/settings.json` (on Windows, a
  silent exit or Store redirect means the launcher is a stub - ask the user to
  install Python before continuing).
- **`WATCH_DIRS` / `SOURCE_EXTENSIONS` in `debt-track.py`**: identical to the
  values set in `docs-track.py` - the two trackers must agree on what counts
  as source.
- **`TEST_COMMAND_PATTERNS`** in `debt-track.py`: from how the repo actually
  runs tests (manifest scripts, CI config, README). Keep the defaults that
  apply, remove none blindly.
- **`REQUIRE_TESTS` / `TEST_SUGGESTION`** in `debt-stop-gate.py`: set
  `REQUIRE_TESTS = True` and fill the suggestion **only** when you observed a
  working test suite (a test script in the manifest, a test config file, or a
  test run you executed). On a repo without tests the gate would fire on
  every coding turn, and a gate that is reliably wrong teaches the agent to
  game gates in general - leave it `False` then.
- **`VERIFY_COMMANDS`** in `debt-stop-gate.py`: the repo's fast checks
  (typecheck, lint), each verified by running it once during setup - never
  add a command you did not see succeed (or fail only on real findings).
  Leave empty if there are none; do not put the full test suite here.
- **`PROTECTED_*`, `HYGIENE_PATTERNS`, `SCOPE_FENCE`** in `edit-guard.py` /
  `debt-stop-gate.py`: keep the defaults unless they conflict with observed
  behavior (e.g. remove the `console.log` pattern for a CLI whose output IS
  `console.log`).

### 3. Fill the CLAUDE.md placeholders

- Project name: from the package manifest or the repo name.
- Description: from the README or the manifest's description field. If neither
  exists, ask the user for one or two sentences. Do **not** compose a
  description from your impression of the code.

### 4. Write the initial docs - one area at a time

Create the hub from `templates/index.md` and one detail doc per area from
`templates/feature.md`, registered in the hub. For **each** doc:

1. **Read the code first** - the area's entry points and main modules. Only
   then write.
2. `## Mechanism` describes only control flow you actually traced; `## Specifics`
   only invariants visible in the code you read.
3. `## Avoid` stays **empty** at setup unless the user names rejected
   approaches - do not fabricate history.
4. Every path in `## Files` and in the hub's registry is verified to exist
   before saving.
5. Before saving, self-check every sentence: name the file (or command output,
   or user answer) that supports it. If you cannot, delete the sentence or turn
   it into a `TODO(verify)`.

If an area is too large to read now, write a short doc covering only what you
read, with `TODO(verify)` markers for the rest, and tell the user which areas
are incomplete.

### 5. Verify

1. Run the audit: `python .claude/skills/docs-audit/docs_audit.py` from the
   target repo root. Fix every finding (see the docs-audit skill) and re-run
   until clean.
2. Confirm the hooks are wired: all seven hook scripts exist (four
   `docs-*.py`, plus `edit-guard.py`, `debt-track.py`, `debt-stop-gate.py`),
   the launcher in `.claude/settings.json` matches step 2, and the paths in
   `settings.json` resolve.
3. Report to the user: what was copied, which values were configured and from
   which observation (e.g. "`WATCH_DIRS = ('app', 'lib')` - from `git ls-files`"),
   which docs were written from which code, and every remaining `TODO(verify)`.
