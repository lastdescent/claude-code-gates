#!/usr/bin/env python3
"""Debt tracker - PostToolUse hook on Read|Write|Edit|MultiEdit|NotebookEdit|Bash.

Maintains the session ledgers that edit-guard.py (PreToolUse) and
debt-stop-gate.py (Stop) act on. The full loop is documented in
docs/gates.md. Ledgers, all keyed by session_id in this directory:

- .debt-tests-<sid>      source files changed since the last test run
- .debt-callsites-<sid>  "path<TAB>symbol" - files that reference a symbol
                         whose definition line changed and that were not
                         visited (Read or edited) since
- .debt-verify-<sid>     source files changed since the last green verify
                         run (presence = the stop gate must run checks)
- .debt-changed-<sid>    every source file changed this session (scope for
                         the diff-hygiene check)
- .debt-docsread-<sid>   every .md file Read this session (read-first gate)
- .debt-visited-<sid>    every file Read this session (call-site noise filter)
- .debt-baseline-<sid>   git snapshot for attributing Bash-made changes

Event handling:
- Read: record visited (+ docsread for .md); visiting a file clears its
  call-site entries.
- Write/Edit: source file -> tests/verify/changed debt. Edit/MultiEdit only:
  definition lines that changed are searched for symbols, and files still
  referencing those symbols (git grep -w) become call-site debt - minus
  files already visited or changed this session.
- Bash: diff `git status --porcelain -uall` against the session baseline
  (same net as docs-track.py) so script/codegen-made changes are tracked
  too. A command matching TEST_COMMAND_PATTERNS that was not interrupted
  clears the test ledger - Bash tool_response carries no exit code, so this
  is deliberately a presence check; VERIFY_COMMANDS in debt-stop-gate.py is
  the hard correctness check.

Per repo: keep WATCH_DIRS / SOURCE_EXTENSIONS identical to docs-track.py,
and set TEST_COMMAND_PATTERNS to how this repo actually runs tests.
"""
import json, os, re, subprocess, sys

WATCH_DIRS = ("src",)
SOURCE_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx", ".py", ".go", ".rs", ".css")
TEST_COMMAND_PATTERNS = ("pytest", "npm test", "npm run test", "yarn test",
                         "pnpm test", "vitest", "jest", "go test",
                         "cargo test", "dotnet test", "rspec", "phpunit")

# Definition-line patterns: (regex with the symbol in group 1, required
# substring or None). Applied only to lines that differ between old_string
# and new_string, so body-only edits never produce call-site debt.
DEF_PATTERNS = (
    (r"^\s*(?:export\s+)?(?:default\s+)?(?:declare\s+)?(?:async\s+)?function\s*\*?\s*([A-Za-z_$][\w$]*)", None),
    (r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*(?::[^=]*)?=", "=>"),
    (r"^\s*export\s+(?:const|let|var)\s+([A-Za-z_$][\w$]*)", None),
    (r"^\s*(?:export\s+)?(?:default\s+)?(?:abstract\s+)?(?:class|interface|enum)\s+([A-Za-z_$][\w$]*)", None),
    (r"^\s*(?:export\s+)?type\s+([A-Za-z_$][\w$]*)\s*=", None),
    (r"^\s*(?:async\s+)?def\s+([A-Za-z_]\w*)\s*\(", None),
    (r"^\s*class\s+([A-Za-z_]\w*)\s*[:(\s]", None),
    (r"^func\s+(?:\([^)]*\)\s*)?([A-Za-z_]\w*)\s*\(", None),
    (r"^\s*(?:pub(?:\([^)]*\))?\s+)?fn\s+([A-Za-z_]\w*)", None),
    (r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:struct|enum|trait)\s+([A-Za-z_]\w*)", None),
)
SYMBOL_STOPLIST = {"main", "init", "test", "tests", "setup", "index",
                   "default", "constructor", "render", "props", "state"}
MIN_SYMBOL_LEN = 4
MAX_SYMBOLS_PER_EDIT = 5
MAX_REFS_PER_SYMBOL = 20

data = json.load(sys.stdin)
sid = data.get("session_id", "default")
tool = data.get("tool_name", "")
tin = data.get("tool_input", {}) or {}
HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(HOOKS_DIR))
led = lambda name: os.path.join(HOOKS_DIR, f".debt-{name}-{sid}")


def to_rel(path):
    if not path:
        return None
    rel = os.path.relpath(os.path.abspath(path), REPO_ROOT).replace("\\", "/")
    return None if rel.startswith("..") else rel


def is_source(rel):
    p = f"/{rel}"
    return rel.endswith(SOURCE_EXTENSIONS) and any(f"/{d}/" in p for d in WATCH_DIRS)


def read_lines(path):
    if not os.path.exists(path):
        return set()
    with open(path, encoding="utf-8") as f:
        return {l.strip() for l in f if l.strip()}


def add_line(path, item):
    if item not in read_lines(path):
        with open(path, "a", encoding="utf-8") as f:
            f.write(item + "\n")


def visit_clears_callsites(rel):
    cs = led("callsites")
    before = read_lines(cs)
    if not before:
        return
    kept = {l for l in before if l.split("\t", 1)[0] != rel}
    # Drop "!capped" markers whose symbol has no real entries left.
    live_syms = {l.split("\t")[1] for l in kept
                 if not l.startswith("!") and l.count("\t") >= 1}
    kept = {l for l in kept
            if not l.startswith("!capped\t") or l.split("\t")[1] in live_syms}
    if kept == before:
        return
    if kept:
        with open(cs, "w", encoding="utf-8") as f:
            f.writelines(l + "\n" for l in sorted(kept))
    else:
        os.remove(cs)


def mark_source_changed(rel):
    for name in ("tests", "verify", "changed"):
        add_line(led(name), rel)


def git_dirty():
    try:
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


def changed_symbols(pairs):
    syms = set()
    for old, new in pairs:
        old_lines = {l.rstrip() for l in (old or "").splitlines() if l.strip()}
        new_lines = {l.rstrip() for l in (new or "").splitlines() if l.strip()}
        for line in (old_lines - new_lines) | (new_lines - old_lines):
            for pat, need in DEF_PATTERNS:
                if need and need not in line:
                    continue
                m = re.match(pat, line)
                if m:
                    syms.add(m.group(1))
    return sorted(s for s in syms
                  if len(s) >= MIN_SYMBOL_LEN and s.lower() not in SYMBOL_STOPLIST)


def grep_refs(sym, self_rel):
    try:
        out = subprocess.run(["git", "grep", "-l", "--untracked", "-w", "-e", sym],
                             cwd=REPO_ROOT, capture_output=True, text=True, timeout=10)
    except Exception:
        return []
    if out.returncode not in (0, 1):
        return []
    skip = read_lines(led("visited")) | read_lines(led("changed")) | {self_rel}
    return [p for p in out.stdout.splitlines()
            if p and p.endswith(SOURCE_EXTENSIONS) and p not in skip]


if tool == "Read":
    rel = to_rel(tin.get("file_path"))
    if rel:
        add_line(led("visited"), rel)
        if rel.endswith(".md"):
            add_line(led("docsread"), rel)
        visit_clears_callsites(rel)
    sys.exit(0)

if tool in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
    rel = to_rel(tin.get("file_path") or tin.get("notebook_path"))
    if not rel:
        sys.exit(0)
    visit_clears_callsites(rel)
    if not is_source(rel):
        sys.exit(0)
    mark_source_changed(rel)
    pairs = []
    if tool == "Edit":
        pairs = [(tin.get("old_string", ""), tin.get("new_string", ""))]
    elif tool == "MultiEdit":
        pairs = [(e.get("old_string", ""), e.get("new_string", ""))
                 for e in tin.get("edits", [])]
    for sym in changed_symbols(pairs)[:MAX_SYMBOLS_PER_EDIT]:
        refs = grep_refs(sym, rel)
        for p in refs[:MAX_REFS_PER_SYMBOL]:
            add_line(led("callsites"), f"{p}\t{sym}")
        if len(refs) > MAX_REFS_PER_SYMBOL:
            add_line(led("callsites"),
                     f"!capped\t{sym}\t{len(refs)} referencing files in total")
    sys.exit(0)

if tool == "Bash":
    dirty = git_dirty()
    baseline = led("baseline")
    if dirty is not None:
        if not os.path.exists(baseline):
            # No snapshot: pre-existing changes cannot be attributed to this
            # session. Establish the baseline now instead of blaming them.
            with open(baseline, "w", encoding="utf-8") as f:
                f.writelines(p + "\n" for p in sorted(dirty))
        else:
            for rel in dirty - read_lines(baseline):
                visit_clears_callsites(rel)
                if is_source(rel):
                    mark_source_changed(rel)
            with open(baseline, "w", encoding="utf-8") as f:
                f.writelines(p + "\n" for p in sorted(dirty))
    cmd = (tin.get("command") or "").lower()
    resp = data.get("tool_response") or {}
    if any(pat in cmd for pat in TEST_COMMAND_PATTERNS):
        exit_code = next((resp.get(k) for k in ("exitCode", "exit_code", "returnCode")
                          if isinstance(resp, dict) and resp.get(k) is not None), None)
        interrupted = isinstance(resp, dict) and resp.get("interrupted")
        if not interrupted and exit_code in (None, 0):
            tests = led("tests")
            if os.path.exists(tests):
                os.remove(tests)
