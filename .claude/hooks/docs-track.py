#!/usr/bin/env python3
"""Docs-pending tracker - PostToolUse hook on Write|Edit|MultiEdit|NotebookEdit|Bash.

Half of the loop that keeps docs in sync with code (the other half is
docs-stop-gate.py; the session baseline comes from docs-session-start.py):

- Write/Edit of a source file (under WATCH_DIRS, with a SOURCE_EXTENSIONS
  extension): append its path to this session's pending file.
- Write/Edit under docs/: delete the pending file and reset the baseline -
  the docs were touched, the debt is considered paid.
- Bash: diff `git status --porcelain` against this session's baseline snapshot,
  so source files changed by shell commands (sed, codegen, git apply, scripts)
  are tracked too, not only Write/Edit. Newly dirty docs files clear the
  pending file the same way a docs Edit does. Without git, or without a
  baseline snapshot, this net is silently disabled; Write/Edit tracking still
  works.

The pending and baseline files are keyed by session_id, so parallel agents in
one repo track and clear only their own edits. The pending file is a presence
check: any docs/ edit clears it. If a change truly touches no documented
behavior, delete the pending file by hand and say so.

Per repo: set WATCH_DIRS / SOURCE_EXTENSIONS to the source layout, and in
.claude/settings.json use the Python launcher that exists - python on Windows,
often python3 on macOS/Linux.
"""
import json, os, subprocess, sys

WATCH_DIRS = ("src",)
SOURCE_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx", ".py", ".go", ".rs", ".css")
DOCS_DIR = "docs"

data = json.load(sys.stdin)
sid = data.get("session_id", "default")
HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(HOOKS_DIR))
pending = os.path.join(HOOKS_DIR, f".docs-pending-{sid}")
baseline = os.path.join(HOOKS_DIR, f".docs-baseline-{sid}")


def in_dir(path, seg):
    p = path.replace("\\", "/")
    return p.startswith(f"{seg}/") or f"/{seg}/" in p


def is_source(path):
    return path.endswith(SOURCE_EXTENSIONS) and any(in_dir(path, d) for d in WATCH_DIRS)


def git_dirty():
    """Repo-relative paths of modified/untracked files; None if git is unavailable."""
    try:
        # -uall: list untracked files individually, not collapsed to their dir
        out = subprocess.run(["git", "status", "--porcelain", "-uall"], cwd=REPO_ROOT,
                             capture_output=True, text=True, timeout=10)
    except Exception:
        return None
    if out.returncode != 0:
        return None
    files = set()
    for line in out.stdout.splitlines():
        p = line[3:].strip().strip('"')
        if " -> " in p:
            p = p.split(" -> ", 1)[1].strip().strip('"')
        if p:
            files.add(p)
    return files


def read_lines(path):
    if not os.path.exists(path):
        return set()
    with open(path, encoding="utf-8") as f:
        return {l.strip() for l in f if l.strip()}


def write_lines(path, items):
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(p + "\n" for p in sorted(items))


def append_lines(path, items):
    with open(path, "a", encoding="utf-8") as f:
        f.writelines(p + "\n" for p in items)


def clear_pending():
    if os.path.exists(pending):
        os.remove(pending)
    dirty = git_dirty()
    if dirty is not None:
        # Reset the baseline: what is dirty now is no longer this session's new debt.
        write_lines(baseline, dirty)


if data.get("tool_name") == "Bash":
    dirty = git_dirty()
    if dirty is None:
        sys.exit(0)
    if not os.path.exists(baseline):
        # No session-start snapshot: pre-existing changes cannot be attributed
        # to this session. Establish the baseline now instead of blaming it.
        write_lines(baseline, dirty)
        sys.exit(0)
    new = dirty - read_lines(baseline)
    if any(in_dir(p, DOCS_DIR) for p in new):
        clear_pending()
    else:
        new_src = sorted(p for p in new if is_source(p))
        if new_src:
            append_lines(pending, new_src)
        write_lines(baseline, dirty)
    sys.exit(0)

path = (data.get("tool_input", {}).get("file_path")
        or data.get("tool_input", {}).get("notebook_path")
        or data.get("tool_response", {}).get("filePath") or "")
if not path:
    sys.exit(0)
if in_dir(path, DOCS_DIR):
    clear_pending()
elif is_source(path):
    append_lines(pending, [path])
