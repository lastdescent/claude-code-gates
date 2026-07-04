#!/usr/bin/env python3
"""Docs-pending gate - Stop hook. If this session's pending file lists source
files changed without a docs/ update, block the turn, name them, and suggest
the owner docs from the source-of-truth registry in docs/index.md. See
docs-track.py for the full loop."""
import json, os, posixpath, re, sys, time

data = json.load(sys.stdin)
HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(HOOKS_DIR))
pending = os.path.join(HOOKS_DIR, f".docs-pending-{data.get('session_id', 'default')}")
if not os.path.exists(pending):
    sys.exit(0)
with open(pending, encoding="utf-8") as f:
    files = list(dict.fromkeys(l.strip() for l in f if l.strip()))
if not files:
    sys.exit(0)

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


def describe(path):
    p = path.replace("\\", "/")
    docs = sorted({doc for prefix, doc in owners if prefix and prefix in p})
    return f"  - {path}" + (f"  -> owner doc: {', '.join(docs)}" if docs else "")


shown = "\n".join(describe(p) for p in files[:10])
if len(files) > 10:
    shown += f"\n  ... and {len(files) - 10} more"
try:
    with open(os.path.join(HOOKS_DIR, ".gate-log.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                            "session": data.get("session_id", "default")[:8],
                            "gate": "docs", "detail": f"{len(files)} file(s) pending"}) + "\n")
except OSError:
    pass
print(json.dumps({"decision": "block", "reason":
    "STOP BLOCKED: source changed without a doc update.\n" + shown +
    "\n\nUpdate the docs these changes affect - suggested owner docs come from the"
    " registry in docs/index.md; check its Topics table for anything unlisted."
    " Only if the change truly touches no documented behavior, delete\n"
    f"{pending}\nand state in your reply why no doc applies."}))
