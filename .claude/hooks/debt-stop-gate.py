#!/usr/bin/env python3
"""Debt gate - Stop hook. Blocks the turn while session debt tracked by
debt-track.py is unresolved, bundling everything into ONE actionable message
(the docs debt has its own gate in docs-stop-gate.py; the full loop is
documented in docs/gates.md). Checks, in order:

1. Call-site debt: definition lines changed, referencing files not visited.
2. Test debt (only if REQUIRE_TESTS): source changed, no test run since.
3. Diff hygiene: debug residue on lines this session added.
4. Verify commands: run only when 1-3 are clean (a blocked turn re-runs the
   gate anyway, so running expensive checks before cheap debt is resolved
   would waste their runtime) and only while .debt-verify-<sid> exists;
   a green run deletes that file so verify is cached until the next change.

Every section names its escape hatch (delete/create the named file AND state
the reason in the reply) - the gate makes silence impossible, it does not
make the judgment. stop_hook_active is deliberately ignored: exiting early
on it would let a turn end with debt by simply stopping twice, and every
block here is resolvable by a named action; the harness's own cap on
consecutive stop blocks is the runaway backstop.

Per repo: set REQUIRE_TESTS/TEST_SUGGESTION when the repo has a test suite,
VERIFY_COMMANDS to the fast checks (typecheck/lint) that must be green, and
tailor HYGIENE_PATTERNS. All checks fail open without git.
"""
import json, os, re, subprocess, sys, time

REQUIRE_TESTS = False           # setup turns this on when the repo has tests
TEST_SUGGESTION = ""            # e.g. "npm test" - shown in the gate message
VERIFY_COMMANDS = ()            # e.g. ("npx tsc --noEmit", "ruff check .")
VERIFY_TOTAL_BUDGET = 240       # seconds across all verify commands
HYGIENE_PATTERNS = (            # (label, regex) applied to added lines
    ("merge conflict marker", r"^(<{7}(\s|$)|={7}$|>{7}(\s|$))"),
    ("debugger statement", r"^\s*debugger\s*;?\s*$"),
    ("python breakpoint", r"\b(breakpoint\(\)|pdb\.set_trace\(\))"),
    ("console.log/debug", r"\bconsole\.(log|debug)\s*\("),
    ("bare TODO/FIXME", r"\b(TODO|FIXME)\b(?!\()"),
)
SHOW_FILES = 8                  # per-section list cap in the gate message

data = json.load(sys.stdin)
sid = data.get("session_id", "default")
HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(HOOKS_DIR))
led = lambda name: os.path.join(HOOKS_DIR, f".debt-{name}-{sid}")


def read_lines(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [l.strip() for l in f if l.strip()]


def log_gate(gate, detail):
    try:
        with open(os.path.join(HOOKS_DIR, ".gate-log.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                "session": sid[:8], "gate": gate, "detail": detail}) + "\n")
    except OSError:
        pass


def listing(items, cap=SHOW_FILES):
    shown = "\n".join(f"  - {i}" for i in items[:cap])
    if len(items) > cap:
        shown += f"\n  ... and {len(items) - cap} more"
    return shown


sections = []

# --- 1. Call-site debt ------------------------------------------------------
cs_lines = read_lines(led("callsites"))
if cs_lines:
    by_sym, capped = {}, {}
    for l in cs_lines:
        parts = l.split("\t")
        if parts[0] == "!capped" and len(parts) >= 3:
            capped[parts[1]] = parts[2]
        elif len(parts) >= 2:
            by_sym.setdefault(parts[1], []).append(parts[0])
    body = ""
    for sym in sorted(by_sym):
        note = f" ({capped[sym]}, list capped)" if sym in capped else ""
        body += f"  `{sym}`{note} is still referenced by unvisited files:\n"
        body += listing(sorted(by_sym[sym])) + "\n"
    if body:
        sections.append((
            "callsites",
            "Changed definitions with unvisited references:\n" + body.rstrip() +
            "\n  -> Read or edit each file and adapt it if needed. Only if the"
            " change cannot affect callers (e.g. purely additive), delete\n"
            f"  {led('callsites')}\n  and state that reasoning in your reply."))

# --- 2. Test debt -----------------------------------------------------------
test_files = read_lines(led("tests"))
if REQUIRE_TESTS and test_files:
    run_hint = f" Run: {TEST_SUGGESTION}" if TEST_SUGGESTION else " Run the test suite."
    sections.append((
        "tests",
        "Source changed with no test run since:\n" + listing(sorted(set(test_files))) +
        f"\n  ->{run_hint} Only if tests truly do not apply, delete\n"
        f"  {led('tests')}\n  and state why in your reply."))

# --- 3. Diff hygiene --------------------------------------------------------
changed = sorted({p for p in read_lines(led("changed"))
                  if os.path.exists(os.path.join(REPO_ROOT, p))})
if changed and not os.path.exists(led("hygiene-skip")):
    findings = []

    def scan(path, text):
        for n, line in enumerate(text.splitlines(), 1):
            for label, pat in HYGIENE_PATTERNS:
                if re.search(pat, line):
                    findings.append(f"{path}:{n}: {label}: {line.strip()[:80]}")

    try:
        st = subprocess.run(["git", "status", "--porcelain", "-uall"], cwd=REPO_ROOT,
                            capture_output=True, text=True, timeout=10)
        untracked = {l[3:].strip().strip('"') for l in st.stdout.splitlines()
                     if l.startswith("??")} if st.returncode == 0 else set()
        tracked = [p for p in changed if p not in untracked]
        if tracked and st.returncode == 0:
            diff = subprocess.run(["git", "diff", "HEAD", "-U0", "--"] + tracked,
                                  cwd=REPO_ROOT, capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", timeout=20)
            if diff.returncode == 0:
                current = None
                for line in diff.stdout.splitlines():
                    if line.startswith("+++ b/"):
                        current = line[6:]
                    elif line.startswith("+") and not line.startswith("+++") and current:
                        for label, pat in HYGIENE_PATTERNS:
                            if re.search(pat, line[1:]):
                                findings.append(
                                    f"{current}: {label}: {line[1:].strip()[:80]}")
        for p in (p for p in changed if p in untracked):
            fp = os.path.join(REPO_ROOT, p)
            if os.path.getsize(fp) < 200_000:
                with open(fp, encoding="utf-8", errors="replace") as f:
                    scan(p, f.read())
    except Exception:
        findings = []  # no git / timeout: this net fails open
    if findings:
        sections.append((
            "hygiene",
            "Debug residue on lines this session added:\n" + listing(findings, 12) +
            "\n  -> Remove it. Only if it is intentional (e.g. a CLI that prints),"
            " create\n"
            f"  {led('hygiene-skip')}\n  and state why in your reply."))

# --- 4. Verify commands (only when everything above is clean) ----------------
if VERIFY_COMMANDS and not sections \
        and os.path.exists(led("verify")) and not os.path.exists(led("verify-skip")):
    deadline = time.monotonic() + VERIFY_TOTAL_BUDGET
    failed = None
    for cmd in VERIFY_COMMANDS:
        budget = deadline - time.monotonic()
        if budget <= 0:
            failed = (cmd, "verify budget exhausted before this command ran", "")
            break
        try:
            run = subprocess.run(cmd, shell=True, cwd=REPO_ROOT, capture_output=True,
                                 text=True, encoding="utf-8", errors="replace",
                                 timeout=budget)
        except subprocess.TimeoutExpired:
            failed = (cmd, "timed out", "")
            break
        if run.returncode != 0:
            out = ((run.stdout or "") + "\n" + (run.stderr or "")).strip()
            tail = "\n".join(out.splitlines()[-25:])[-1800:]
            failed = (cmd, f"exit {run.returncode}", tail)
            break
    if failed:
        cmd, status, tail = failed
        sections.append((
            "verify",
            f"Verify failed: `{cmd}` ({status})\n" + (tail + "\n" if tail else "") +
            "  -> Fix the errors until it passes. Only if that is impossible right"
            " now (e.g. pre-existing breakage), create\n"
            f"  {led('verify-skip')}\n  and state why in your reply."))
    else:
        os.remove(led("verify"))
        log_gate("verify", "green")

if not sections:
    sys.exit(0)

for gate, _ in sections:
    log_gate(gate, "blocked")
deferred = ("\n\nNote: verify commands are configured and will run once the"
            " debt above is resolved.") \
    if VERIFY_COMMANDS and os.path.exists(led("verify")) \
    and not any(g == "verify" for g, _ in sections) \
    and not os.path.exists(led("verify-skip")) else ""
reason = ("STOP BLOCKED: unresolved debt from this session's changes.\n\n"
          + "\n\n".join(f"[{i}] {text}" for i, (_, text) in enumerate(sections, 1))
          + deferred)
print(json.dumps({"decision": "block", "reason": reason}))
