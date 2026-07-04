---
name: docs-audit
description: Check the project docs for drift - dead code paths, dead links, unregistered docs, oversized docs, code newer than its doc. Use only when the user explicitly asks to audit or lint the docs, or as the final step of docs-setup - never proactively.
---

# Audit the docs

The audit runs **inline, in the current session and working tree**, and only
on explicit request (or as the final step of docs-setup). Do not propose it as
a recurring or background task, do not queue findings as follow-up tasks, and
do not run it in a separate worktree - fix the findings here, now.

1. Run the checker from the repo root:

   ```
   python .claude/skills/docs-audit/docs_audit.py
   ```

   It scans every markdown file in `docs/` directories and reports: dead code
   paths, dead relative links, docs over the size budget, code committed after
   its doc's last commit, and detail docs not linked from their hub. Exit code
   1 means findings, 0 means clean.

2. Fix the findings - under the grounding rule in `.claude/rules/style.md`:
   read the code before touching the doc.

   - **Dead code path** -> find where the code moved (`git log --follow`,
     Glob) and update the path. If the feature is gone, remove or merge the
     section and its registry row.
   - **Code newer than doc** -> read the newer commits' diff for that path and
     update only what actually changed. If nothing documented changed, a
     doc-only touch-up commit is acceptable to reset the comparison.
   - **Dead link** -> repoint it to the current location of the target.
   - **Not linked from the hub** -> register the doc in the Topics table (and
     in the registry if it owns a cross-cutting concept).
   - **Oversized doc** -> split by concept per `.claude/rules/style.md` and
     register both halves.

3. Re-run until clean. Never silence a finding by weakening the doc (removing
   a Files row, deleting a section) unless the code is really gone.
