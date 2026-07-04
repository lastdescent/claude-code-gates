# Edit guards & debt gates

Extends the docs enforcement loop with deterministic guards *before* edits and
a bundled debt gate at turn end. Same design as the docs loop: state lives in
session-keyed ledger files on disk (it survives compaction and distraction),
gates fire at the moment of decision with the cheapest correct exit named in
the message, judgment stays with the agent via explicit escape hatches. Three
stdlib-Python scripts in `.claude/hooks/`, wired in `.claude/settings.json`;
the session lifecycle (cleanup, baselines, compact digest) is handled by the
shared scripts owned by [enforcement.md](enforcement.md).

## Mechanism

1. **PreToolUse** on `Write|Edit|MultiEdit|NotebookEdit` - `edit-guard.py`,
   three checks in order:
   - **Protected paths**: lock/generated files (`PROTECTED_SUFFIXES`,
     `PROTECTED_DIR_SEGMENTS`) are denied. If `.debt-protected-ok-<sid>`
     exists, it is consumed and the edit passes all checks - a one-shot
     override for edits the user explicitly asked for.
   - **Read-first**: an edit under a `Code source` prefix of the registry in
     `docs/index.md` is denied while any of its owner docs is missing from
     the `.debt-docsread-<sid>` ledger. The deny message names the doc(s);
     Reading them and retrying resolves it. This makes the read-first rule in
     `.claude/rules/docs.md` deterministic instead of hoped-for.
   - **Scope fence**: the first edit in a top-level directory the session has
     not edited yet is denied once with a warning; retrying passes and the
     directory joins `.debt-scope-<sid>`. Cross-area side effects become
     explicit decisions. `docs/` and root-level files are exempt; a
     read-first deny pre-marks the fence so one edit is denied at most once.
2. **PostToolUse** on `Read|Write|Edit|MultiEdit|NotebookEdit|Bash` -
   `debt-track.py` maintains the ledgers:
   - Read records the file in `.debt-visited-<sid>` (and `.md` files in
     `.debt-docsread-<sid>`); visiting a file clears its call-site entries.
   - Write/Edit of a source file (under `WATCH_DIRS` with a
     `SOURCE_EXTENSIONS` extension) appends it to the tests/verify/changed
     ledgers. For Edit/MultiEdit, definition lines that differ between
     `old_string` and `new_string` are matched against `DEF_PATTERNS`; files
     still referencing a changed symbol (`git grep -l --untracked -w`) become
     call-site debt, minus files already visited or changed this session.
   - Bash diffs `git status --porcelain -uall` against `.debt-baseline-<sid>`
     so script/codegen-made source changes are tracked too. A command
     matching `TEST_COMMAND_PATTERNS` that was not interrupted deletes the
     test ledger.
3. **Stop** - `debt-stop-gate.py` bundles all open debt into one block
   message, each section with its escape hatch: call-site debt, test debt
   (only if `REQUIRE_TESTS`), diff hygiene (`HYGIENE_PATTERNS` against lines
   this session added - `git diff HEAD -U0` for tracked, full scan for
   untracked files), then `VERIFY_COMMANDS` - run only when the other
   sections are clean and only while `.debt-verify-<sid>` exists; a green
   run deletes that file, so verify is cached until the next source change.
4. Every fired gate appends a line to `.gate-log.jsonl`
   (`{ts, session, gate, detail}`), including the docs gate. The log is the
   self-tuning signal: a gate that fires repeatedly for the same area marks
   a missing doc, rule, or config. Rotated past ~1 MB by the session-start
   script; deliberately kept across sessions.

## Specifics

### Ledger files

All in `.claude/hooks/`, keyed by `session_id`, gitignored, one path (or
`path<TAB>symbol`) per line. Cleaned up by the shared session scripts.

| Ledger | Written by | Meaning |
|--------|-----------|---------|
| `.debt-tests-<sid>` | debt-track | source changed since last test run |
| `.debt-callsites-<sid>` | debt-track | unvisited files referencing a changed symbol; `!capped` lines mark truncated reference lists |
| `.debt-verify-<sid>` | debt-track | presence = verify must run (file may be empty; content is informational) |
| `.debt-changed-<sid>` | debt-track | all source changed this session (hygiene scope) |
| `.debt-docsread-<sid>` | debt-track | `.md` files Read (read-first gate) |
| `.debt-visited-<sid>` | debt-track | all files Read (call-site noise filter) |
| `.debt-baseline-<sid>` | session-start / debt-track | git snapshot for the Bash net |
| `.debt-scope-<sid>`, `.debt-scope-warned-<sid>` | edit-guard | fence state |
| `.debt-protected-ok-<sid>`, `.debt-verify-skip-<sid>`, `.debt-hygiene-skip-<sid>` | agent (escape hatches) | explicit overrides |

### Presence semantics and escapes

Like the docs gate, these gates verify that something happened, not that the
*right* thing happened - that judgment stays with the agent. Every escape is
explicit and auditable: delete the named ledger (call-sites, tests) or create
the named skip file (verify, hygiene, protected), **and state the reasoning
in the reply**. A gate whose message does not name the cheapest correct exit
produces flailing or gaming; these always do.

### Configuration

Per-repo constants at the top of each script; docs-setup sets them from
observed facts. `WATCH_DIRS`/`SOURCE_EXTENSIONS` must stay identical in
`docs-track.py` and `debt-track.py`. `REQUIRE_TESTS` defaults to **off**: on
a repo without a test suite the gate would fire on every coding turn, and a
gate that is reliably wrong trains the agent to game gates in general.
`VERIFY_COMMANDS` defaults to empty for the same reason; give it the repo's
fast checks (typecheck, lint), not the full test suite, and mind
`VERIFY_TOTAL_BUDGET` and the Stop hook `timeout` in `.claude/settings.json`.
In this toolkit repo there is no `src/`, so everything except the read-first
gate and the scope fence is inert.

### Registry contract

The read-first gate parses the registry rows of `docs/index.md` (concept,
level, owner-doc markdown link, backticked code path) with the same regex as
the docs stop gate. Prefix matching is boundary-aware (`rel == prefix` or
`rel.startswith(prefix + "/")`), stricter than the stop gate's substring
match on purpose: a suggesting gate may over-match, a blocking gate must not.
Owner docs that do not exist on disk are skipped (fail open; the audit
catches stale registry rows). Editing an owner doc itself is never blocked
by its own row, and `docs/` paths bypass the guard entirely - the docs gate
demands exactly those edits.

### Failure behavior

Without git (or on timeout) the Bash net, call-site grep, hygiene and the
baseline silently disable; Write/Edit tracking and the other gates keep
working. On allow, `edit-guard.py` exits 0 **without** output - emitting
`permissionDecision: "allow"` would bypass the user's permission prompts.
Deny messages are sent as both `permissionDecisionReason` and
`additionalContext`, so the agent sees them regardless of which field the
client surfaces. Bash `tool_response` carries no exit code (only
stdout/stderr/interrupted), so a matched, uninterrupted test command counts
as a run - the test gate is deliberately a nudge; `VERIFY_COMMANDS` is the
hard correctness check.

## Avoid

- Emitting `permissionDecision: "allow"` from the guard -> auto-approves
  edits and bypasses the user's permission prompts; allow is exit 0 with no
  output.
- Exiting 0 when `stop_hook_active` is set -> a turn could end with open
  debt by simply stopping twice; every block here is resolvable by a named
  action, and the harness's own cap on consecutive stop blocks is the
  runaway backstop.
- Parsing Bash stdout/stderr to decide whether tests passed -> no exit code
  is available and output formats vary; presence check plus verify commands
  instead.
- Call-site detection on Write or on bare `name(...)` method lines -> Write
  has no old/new diff and method patterns fire on `if`/`for`/test DSLs; only
  definition lines that changed between `old_string` and `new_string` count.
- Fencing root-level files or `docs/` -> fires on routine edits and teaches
  the agent to treat fence messages as noise.
- Running verify while other debt is open -> the blocked turn re-runs the
  gate anyway, so expensive checks would run repeatedly for nothing; verify
  waits until the cheap debt is resolved.
- Sharing one ledger file across sessions -> parallel agents clear each
  other's debt; every ledger is keyed by `session_id`.

## Files

| Role | Path |
|------|------|
| Pre-edit guard (protected, read-first, fence) | `.claude/hooks/edit-guard.py` |
| Ledger maintenance (PostToolUse) | `.claude/hooks/debt-track.py` |
| Bundled debt gate (Stop) | `.claude/hooks/debt-stop-gate.py` |
| Session lifecycle (cleanup, baselines, compact digest) | `.claude/hooks/docs-session-start.py`, `.claude/hooks/docs-session-end.py` (owned by [enforcement.md](enforcement.md)) |
| Hook wiring incl. Stop timeout | `.claude/settings.json` |
| Ignore rules for ledgers and gate log | `.gitignore` |
