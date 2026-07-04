# claude-code-gates Documentation

Hub and source-of-truth registry for the **toolkit itself** - the files in this
repo, not a target project. When setting the system up in another repo, the hub
template is [`templates/index.md`](../templates/index.md); do not copy this file.

## How knowledge is organized

Single-package repo, one level (`docs/`). The rules in
[`.claude/rules/`](../.claude/rules/) and the skills in
[`.claude/skills/`](../.claude/skills/) describe themselves and act as their own
owner docs; only the hook machinery needs a separate doc.

## Source-of-truth registry

| Concept | Level | Owner doc | Code source |
|---------|-------|-----------|-------------|
| Enforcement loop (baseline -> track -> gate) | 1 | [enforcement.md](enforcement.md) | `.claude/hooks/` |
| Edit guards & session debt gates (read-first, call-sites, verify, hygiene, gate log) | 1 | [gates.md](gates.md) | `.claude/hooks/` |
| Doc style, placement & grounding rules | 1 | [style.md](../.claude/rules/style.md) | `.claude/rules/style.md` |
| Setup procedure & grounding contract | 1 | [docs-setup](../.claude/skills/docs-setup/SKILL.md) | `.claude/skills/docs-setup/` |
| Drift audit | 1 | [docs-audit](../.claude/skills/docs-audit/SKILL.md) | `.claude/skills/docs-audit/` |

## Topics

| Topic | Doc |
|-------|-----|
| Enforcement hooks | [enforcement.md](enforcement.md) |
| Edit guards & debt gates | [gates.md](gates.md) |
