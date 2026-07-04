#!/usr/bin/env python3
"""Edit guard - PreToolUse hook on Write|Edit|MultiEdit|NotebookEdit.

Three checks, in order, before an edit tool runs (the ledgers it reads are
written by debt-track.py; the full loop is documented in docs/gates.md):

1. Protected paths: lock/generated files are denied. A one-shot override
   file (.debt-protected-ok-<sid>) lets the next protected edit through
   when the user explicitly asked for one.
2. Read-first: editing a file inside an area that has an owner doc in the
   registry (docs/index.md) is denied until that owner doc was Read this
   session (ledger .debt-docsread-<sid>). The deny reason names the doc;
   reading it and retrying resolves the block. docs-session-start.py resets
   the ledger after a compaction, so the re-read is enforced, not hoped for.
3. Scope fence: the first edit in a top-level directory the session has not
   edited before is denied once with a warning; retrying the same edit
   passes and the directory joins the session scope. This turns cross-area
   side effects into explicit decisions instead of accidents.

Allow is expressed by exiting 0 WITHOUT output - emitting a JSON
permissionDecision "allow" would bypass the user's normal permission
prompts, which this guard must never do. Deny messages are sent as both
permissionDecisionReason and additionalContext so the agent sees them
regardless of which field the client surfaces.
"""
import json, os, posixpath, re, sys, time

PROTECTED_SUFFIXES = (
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "bun.lockb",
    "Cargo.lock", "poetry.lock", "uv.lock", "composer.lock", "Gemfile.lock",
    ".min.js", ".min.css",
)
PROTECTED_DIR_SEGMENTS = ("node_modules", "dist", ".next", "target", "vendor")
SCOPE_FENCE = True
FENCE_EXEMPT_TOP = ("docs",)  # docs edits are demanded by the docs gate - never fence them

data = json.load(sys.stdin)
sid = data.get("session_id", "default")
HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(HOOKS_DIR))
docsread = os.path.join(HOOKS_DIR, f".debt-docsread-{sid}")
scope = os.path.join(HOOKS_DIR, f".debt-scope-{sid}")
warned = os.path.join(HOOKS_DIR, f".debt-scope-warned-{sid}")
protected_ok = os.path.join(HOOKS_DIR, f".debt-protected-ok-{sid}")


def read_lines(path):
    if not os.path.exists(path):
        return set()
    with open(path, encoding="utf-8") as f:
        return {l.strip() for l in f if l.strip()}


def append_line(path, item):
    with open(path, "a", encoding="utf-8") as f:
        f.write(item + "\n")


def log_gate(gate, detail):
    try:
        with open(os.path.join(HOOKS_DIR, ".gate-log.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                "session": sid[:8], "gate": gate, "detail": detail}) + "\n")
    except OSError:
        pass


def deny(gate, msg):
    log_gate(gate, msg.splitlines()[0][:200])
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": msg,
        "additionalContext": msg}}))
    sys.exit(0)


path = (data.get("tool_input", {}).get("file_path")
        or data.get("tool_input", {}).get("notebook_path") or "")
if not path:
    sys.exit(0)
rel = os.path.relpath(os.path.abspath(path), REPO_ROOT).replace("\\", "/")
if rel.startswith(".."):
    sys.exit(0)  # outside the repo (scratchpad etc.) - not this guard's business
parts = rel.split("/")

# --- 1. Protected paths -----------------------------------------------------
if rel.endswith(PROTECTED_SUFFIXES) or any(seg in PROTECTED_DIR_SEGMENTS for seg in parts[:-1]):
    if os.path.exists(protected_ok):
        # One-shot override, consumed. The user explicitly authorized this
        # edit - running the remaining checks against it would only add noise.
        os.remove(protected_ok)
        sys.exit(0)
    else:
        deny("protected", (
            f"EDIT BLOCKED: `{rel}` is a protected (generated/lock) file. Change it"
            " through its owning tool (package manager, build, codegen) instead."
            " Only if the user explicitly asked for a manual edit: create\n"
            f"{protected_ok}\n(e.g. via Bash touch) and retry - the next protected"
            " edit passes."))

# Docs are always editable - the docs stop gate demands exactly that.
if "docs" in parts[:-1]:
    sys.exit(0)

# --- 2. Read-first ----------------------------------------------------------
# Registry rows look like: | Concept | 1 | [auth.md](auth.md) | `src/auth/` |
owners = []  # (code path prefix, repo-relative owner doc)
index_md = os.path.join(REPO_ROOT, "docs", "index.md")
row = re.compile(r"^\|[^|]*\|[^|]*\|\s*\[[^\]]*\]\(([^)#]+)[^)]*\)\s*\|\s*`([^`]+)`")
if os.path.exists(index_md):
    with open(index_md, encoding="utf-8") as f:
        for line in f:
            m = row.match(line.strip())
            if m:
                doc = posixpath.normpath(posixpath.join("docs", m.group(1).strip()))
                owners.append((m.group(2).strip().strip("/"), doc))

read_set = read_lines(docsread)
unread = sorted({doc for prefix, doc in owners
                 if prefix and (rel == prefix or rel.startswith(prefix + "/"))
                 and doc != rel and doc not in read_set
                 and os.path.exists(os.path.join(REPO_ROOT, doc))})
if unread:
    if SCOPE_FENCE and len(parts) > 1 and parts[0] not in read_lines(scope):
        append_line(warned, parts[0])  # one deny cycle per edit: pre-clear the fence
    deny("read-first", (
        f"EDIT BLOCKED (read-first): `{rel}` belongs to an area whose owner doc(s)"
        " you have not read this session:\n"
        + "\n".join(f"  - {d}" for d in unread)
        + "\nRead them with the Read tool, then retry this edit - it will pass."
        " (After a context compaction this resets deliberately: re-reading is required.)"))

# --- 3. Scope fence ---------------------------------------------------------
# Root-level files (README, .gitignore, manifests) are not areas - fencing
# them would fire on routine incidental edits and teach the agent to treat
# fence messages as noise.
if SCOPE_FENCE and len(parts) > 1 and parts[0] not in FENCE_EXEMPT_TOP:
    seen = read_lines(scope)
    if not seen or parts[0] in seen:
        if not seen:
            append_line(scope, parts[0])
        sys.exit(0)
    if parts[0] in read_lines(warned):
        append_line(scope, parts[0])  # confirmed by retry - joins the session scope
        sys.exit(0)
    append_line(warned, parts[0])
    deny("scope-fence", (
        f"EDIT PAUSED (scope fence): first edit outside this session's working"
        f" area(s) [{', '.join(sorted(seen))}] -> new area `{parts[0]}`."
        " If this cross-area change is intended, retry the same edit - it will"
        " pass and the area joins the session scope. This fence exists to make"
        " cross-area side effects explicit, not to forbid them."))
