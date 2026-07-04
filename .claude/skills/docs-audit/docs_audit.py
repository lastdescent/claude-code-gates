#!/usr/bin/env python3
"""Docs drift audit. The repo root is derived from this script's location
(.claude/skills/docs-audit/), so it can be run from anywhere.

Scans every markdown file inside a `docs/` directory (any level) and reports:
  - dead code paths: backticked tokens containing '/' that do not exist on disk
  - dead relative markdown links
  - docs larger than MAX_DOC_LINES (split per .claude/rules/style.md)
  - freshness: code paths committed after the doc's last commit
  - detail docs not linked from the index.md next to them

SKIP_DIRS also skips `examples/` and `templates/` so the shipped example
project and the doc skeletons do not produce findings here (the example's
docs are audited in the repo they were written in); adjust if the target
repo keeps real docs there. Exit code: 1 with findings, 0 when clean. Stdlib only.
"""
import os, re, subprocess, sys

MAX_DOC_LINES = 200
SKIP_DIRS = {".git", ".claude", "node_modules", "vendor", "dist", "build",
             "target", ".next", "examples", "templates"}

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))

CODE_TOKEN = re.compile(r"`([^`\n]+)`")
LINK = re.compile(r"\[[^\]]*\]\(([^)#]+)(?:#[^)]*)?\)")
PATHLIKE = re.compile(r"[A-Za-z0-9_.\-/\\]+")


def rel(p):
    return os.path.relpath(p, ROOT).replace(os.sep, "/")


def git_ts(repo_rel_path):
    """Unix time of the last commit touching the path; None if untracked/no git."""
    try:
        out = subprocess.run(
            ["git", "log", "-1", "--format=%ct", "--", repo_rel_path],
            cwd=ROOT, capture_output=True, text=True, timeout=15)
        s = out.stdout.strip()
        return int(s) if out.returncode == 0 and s else None
    except Exception:
        return None


docs = []
for dirpath, dirnames, filenames in os.walk(ROOT):
    dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
    if "docs" in rel(dirpath).split("/"):
        docs.extend(os.path.join(dirpath, fn)
                    for fn in filenames if fn.endswith(".md"))

findings = []


def finding(doc, msg):
    findings.append(f"{rel(doc)}: {msg}")


for doc in sorted(docs):
    with open(doc, encoding="utf-8") as f:
        text = f.read()
    doc_dir = os.path.dirname(doc)

    n_lines = text.count("\n") + 1
    if n_lines > MAX_DOC_LINES:
        finding(doc, f"{n_lines} lines (> {MAX_DOC_LINES}) - split per style.md")

    # Backticked code paths: must look like a plain path with at least two
    # segments - single-segment tokens like `src/` are usually illustrative.
    live_paths = []
    for tok in sorted(set(CODE_TOKEN.findall(text))):
        tok = tok.strip()
        if not PATHLIKE.fullmatch(tok) or tok.startswith("http"):
            continue
        cand = tok.replace("\\", "/").rstrip("/")
        if "/" not in cand:
            continue
        if os.path.exists(os.path.join(ROOT, cand)):
            live_paths.append(cand)
        elif os.path.exists(os.path.join(doc_dir, cand)):
            live_paths.append(rel(os.path.join(doc_dir, cand)))
        else:
            finding(doc, f"dead code path `{tok}`")

    # Relative markdown links.
    for target in sorted(set(LINK.findall(text))):
        t = target.strip()
        if not t or t.startswith(("http://", "https://", "mailto:")):
            continue
        if not os.path.exists(os.path.normpath(os.path.join(doc_dir, t))):
            finding(doc, f"dead link ({t})")

    # Freshness: code committed after the doc's last commit.
    doc_ts = git_ts(rel(doc))
    if doc_ts:
        stale = [p for p in live_paths if (git_ts(p) or 0) > doc_ts]
        for p in stale[:5]:
            finding(doc, f"code newer than doc: `{p}` changed after the doc's last commit")
        if len(stale) > 5:
            finding(doc, f"... and {len(stale) - 5} more paths newer than the doc")

    # Registration: every detail doc is linked from the index.md next to it.
    name = os.path.basename(doc)
    if name != "index.md":
        hub = os.path.join(doc_dir, "index.md")
        if not os.path.exists(hub):
            finding(doc, f"no hub next to it ({rel(hub)} missing)")
        else:
            with open(hub, encoding="utf-8") as f:
                hub_text = f.read()
            if f"({name}" not in hub_text and f"/{name}" not in hub_text:
                finding(doc, f"not linked from {rel(hub)}")

if findings:
    print(f"{len(findings)} finding(s):")
    print("\n".join("  - " + f for f in findings))
    sys.exit(1)
print(f"OK - {len(docs)} doc(s) clean.")
