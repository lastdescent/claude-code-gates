#!/usr/bin/env python3
"""Session cleanup - SessionEnd hook.

Deletes this session's tracking files (.docs-* pending/baseline and every
.debt-* ledger). The Stop gates have already run on every turn, so when the
session ends its tracking state is obsolete - leaving it behind is what the
age-based cleanup in docs-session-start.py otherwise has to mop up. Sessions
that crash before SessionEnd fires are still covered by that age-based
cleanup. The cross-session .gate-log.jsonl is deliberately kept.
"""
import json, os, sys

data = json.load(sys.stdin)
sid = data.get("session_id", "default")
HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))

for name in os.listdir(HOOKS_DIR):
    if name.startswith((".docs-", ".debt-")) and name.endswith(sid):
        try:
            os.remove(os.path.join(HOOKS_DIR, name))
        except OSError:
            pass
