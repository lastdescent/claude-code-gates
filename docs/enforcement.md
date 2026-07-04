# Enforcement hooks

The hook loop that forces "update the docs in the same turn as the code". Four
stdlib-Python scripts in `.claude/hooks/`, wired in `.claude/settings.json`.
The pre-edit guards and the session debt gates that extend this loop are owned
by [gates.md](gates.md); the session scripts below serve both systems.

## Mechanism

1. **SessionStart** - `docs-session-start.py` deletes `.docs-*`/`.debt-*`
   session files older than 7 days (crashed sessions), rotates
   `.gate-log.jsonl` past ~1 MB, removes empty leftover directories
   under the `worktrees` directory inside `.claude` - runtime debris of Claude
   Code task runs; `os.rmdir` never touches non-empty, i.e. active, worktrees -
   snapshots the repo's
   dirty files (`git status --porcelain -uall`) into this session's two
   baseline files (`.docs-baseline-<sid>` and `.debt-baseline-<sid>`), and -
   when the session (re)starts with `source == "compact"` - injects a
   reminder that the docs system is still binding, plus a digest of the open
   obligations read from the ledgers (which live on disk and survive the
   compaction), and resets the `.debt-docsread-<sid>` ledger so the
   read-first guard in [gates.md](gates.md) enforces re-reading the detail
   docs.
2. **PostToolUse** on `Write|Edit|MultiEdit|NotebookEdit|Bash` -
   `docs-track.py`:
   - Write/Edit of a watched source file -> path appended to the pending file.
   - Write/Edit under `docs/` -> pending file deleted, baseline reset to the
     current dirty set (the debt is paid; what is dirty now is not new debt).
   - Bash -> current dirty set diffed against the baseline; newly dirty source
     files are appended to the pending file, newly dirty docs files clear it.
     This catches edits made via `sed`, codegen, `git apply`, or scripts.
3. **Stop** - `docs-stop-gate.py` blocks the turn while the pending file is
   non-empty, lists the changed source files, and suggests owner docs by
   matching the files against the `Code source` column of the registry in
   `docs/index.md`. Each block also appends a line to the gate log owned by
   [gates.md](gates.md).
4. **SessionEnd** - `docs-session-end.py` deletes this session's `.docs-*`
   and `.debt-*` files: the Stop gates have run on every turn, so the
   tracking state is obsolete once the session ends. Sessions that crash
   before SessionEnd fires are covered by the age-based cleanup in step 1.
   The cross-session `.gate-log.jsonl` is kept.

## Specifics

### Session files

`.docs-pending-<session_id>` and `.docs-baseline-<session_id>` live in
`.claude/hooks/` and are gitignored. Both hold one repo-relative (or, from
Write/Edit, absolute) path per line. Keying by `session_id` lets parallel
agents in one repo track and clear only their own edits. The `.debt-*`
ledgers next to them belong to the guards and gates owned by
[gates.md](gates.md).

### Presence semantics

The pending file is a presence check: **any** docs edit clears the whole list.
The gate cannot verify that the *right* doc was updated - that judgment stays
with the agent; the gate only makes silence impossible. The manual escape hatch
(delete the pending file when no documented behavior changed) is deliberate and
must be stated in the reply.

### Configuration

`WATCH_DIRS` and `SOURCE_EXTENSIONS` at the top of `docs-track.py` define what
counts as source. The toolkit ships the generic default (`("src",)`) for
copying into targets; the toolkit repo itself has no `src/`, so the gate is
inert here. The Python launcher name (`python` vs `python3`) is set in
`.claude/settings.json`.

### Failure behavior

Every git call is wrapped: without git, outside a repo, or on timeout, the
Bash-tracking net and the baseline snapshot silently disable while Write/Edit
tracking keeps working. A missing baseline on the first Bash call is
established from the current dirty set instead of blaming the session for
pre-existing changes.

## Avoid

- Parsing Bash command strings to guess which files they modify -> unreliable;
  the baseline diff of `git status --porcelain -uall` is the mechanism.
- `git status --porcelain` without `-uall` -> collapses untracked directories
  to `dir/`, so newly generated source files escape the net.
- Snapshotting or blaming without a session-start baseline -> attributes
  pre-existing dirty files to the wrong session.
- Clearing the pending file from a hook on Stop -> defeats the gate; only docs
  edits (or the stated manual escape) clear it. Deleting it on SessionEnd is
  different: every turn has already passed the gate by then.
- Splitting docs maintenance into background tasks or separate worktrees ->
  each started task spawns its own worktree and the doc drifts meanwhile; the
  rule in `.claude/rules/docs.md` requires docs work to stay inline.
- A single shared pending file for all sessions -> parallel agents clear each
  other's debt.

## Files

| Role | Path |
|------|------|
| Session housekeeping, baseline, compact reminder | `.claude/hooks/docs-session-start.py` |
| Change tracker (Write/Edit + Bash net) | `.claude/hooks/docs-track.py` |
| Stop gate with owner-doc suggestions | `.claude/hooks/docs-stop-gate.py` |
| Session-end cleanup of tracking files | `.claude/hooks/docs-session-end.py` |
| Hook wiring | `.claude/settings.json` |
| Ignore rules for session files | `.gitignore` |
