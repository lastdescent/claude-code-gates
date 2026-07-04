#!/usr/bin/env python3
"""Session housekeeping - SessionStart hook. Five jobs:

1. Remove .docs-*/.debt-* session files older than MAX_AGE_DAYS (leftovers
   of crashed or abandoned sessions), and rotate .gate-log.jsonl when it
   grows past ~1 MB.
2. Remove empty leftover directories under .claude/worktrees/ - Claude Code
   creates them for isolated task runs and normally cleans them up; an empty
   one is debris. os.rmdir only removes empty directories, so active
   worktrees are never touched.
3. Snapshot the repo's currently dirty files as this session's baseline
   (one copy for docs-track.py, one for debt-track.py), so Bash-made
   changes are attributed to this session without blaming pre-existing ones.
4. After a compaction (source == "compact"), remind the agent that the docs
   system is still binding - the compacted summary is not a substitute for
   the detail docs - and re-inject the open obligations from the ledgers,
   which live on disk and survive the compaction.
5. After a compaction, delete this session's .debt-docsread ledger: the docs
   read before the compaction are no longer in context, so edit-guard.py
   must enforce re-reading them (rule in .claude/rules/docs.md).
"""
import json, os, subprocess, sys, time

MAX_AGE_DAYS = 7

data = json.load(sys.stdin)
sid = data.get("session_id", "default")
HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(HOOKS_DIR))

now = time.time()
for name in os.listdir(HOOKS_DIR):
    if name.startswith((".docs-", ".debt-")):
        p = os.path.join(HOOKS_DIR, name)
        try:
            if now - os.path.getmtime(p) > MAX_AGE_DAYS * 86400:
                os.remove(p)
        except OSError:
            pass

gate_log = os.path.join(HOOKS_DIR, ".gate-log.jsonl")
try:
    if os.path.exists(gate_log) and os.path.getsize(gate_log) > 1_000_000:
        os.replace(gate_log, gate_log + ".old")
except OSError:
    pass

wt_root = os.path.join(REPO_ROOT, ".claude", "worktrees")
if os.path.isdir(wt_root):
    for name in os.listdir(wt_root):
        try:
            os.rmdir(os.path.join(wt_root, name))
        except OSError:
            pass

try:
    # -uall: list untracked files individually, not collapsed to their dir
    out = subprocess.run(["git", "status", "--porcelain", "-uall"], cwd=REPO_ROOT,
                         capture_output=True, text=True, timeout=10)
    if out.returncode == 0:
        files = set()
        for line in out.stdout.splitlines():
            p = line[3:].strip().strip('"')
            if " -> " in p:
                p = p.split(" -> ", 1)[1].strip().strip('"')
            if p:
                files.add(p)
        for name in (f".docs-baseline-{sid}", f".debt-baseline-{sid}"):
            with open(os.path.join(HOOKS_DIR, name), "w", encoding="utf-8") as f:
                f.writelines(p + "\n" for p in sorted(files))
except Exception:
    pass


def ledger(name):
    p = os.path.join(HOOKS_DIR, f"{name}-{sid}")
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as f:
        return [l.strip() for l in f if l.strip()]


if data.get("source") == "compact":
    try:
        # Docs read before the compaction are out of context now - reset the
        # ledger so edit-guard.py enforces the re-read instead of hoping.
        os.remove(os.path.join(HOOKS_DIR, f".debt-docsread-{sid}"))
    except OSError:
        pass
    debts = []
    pending = ledger(".docs-pending")
    if pending:
        debts.append("docs update still pending for: " + ", ".join(pending[:10]))
    tests = ledger(".debt-tests")
    if tests:
        debts.append("no test run since changes to: " + ", ".join(sorted(set(tests))[:10]))
    syms = sorted({l.split("\t")[1] for l in ledger(".debt-callsites")
                   if not l.startswith("!") and "\t" in l})
    if syms:
        debts.append("changed definitions with unvisited references: " + ", ".join(syms[:10]))
    # Presence check, matching debt-stop-gate.py - the file may be empty.
    if os.path.exists(os.path.join(HOOKS_DIR, f".debt-verify-{sid}")):
        debts.append("verify checks have not passed since the last source change")
    digest = (" Open obligations carried over from before the compaction:\n- "
              + "\n- ".join(debts) + "\nResolve them before ending the turn;"
              " the stop gates will hold them either way.") if debts else ""
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext":
            "Context was compacted. The documentation system is still binding:"
            " docs/index.md and the rules in .claude/rules/ govern every coding"
            " task. Re-open the detail docs for the area you are working on"
            " before further code changes - the summary is not a substitute -"
            " and keep updating docs in the same turn as code. The read-before-"
            "edit ledger was reset: owner docs must be Read again before edits"
            " in their areas." + digest}}))
