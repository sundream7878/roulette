# Cursor Rules Quick Guide

## 1) Project rule (recommended)
Put rule files in:

- `.cursor/rules/*.mdc`

Use this minimum format:

```md
---
description: Basic guardrails for this project
alwaysApply: true
---

# Rule Title

- Keep changes small and reversible.
- Fix one issue at a time.
```

`alwaysApply: true` means Cursor should read it in every session for this project.

## 2) Global rule (all projects)
If you want the same baseline in every new project, add a short global rule in Cursor User Rules (Settings).

Suggested global baseline:

- One issue per commit
- No speculative multi-fix
- Verify before claiming done
- Prefer rollback-safe changes

## 3) Team workflow suggestion
- Keep global rules short and generic.
- Keep project rules specific (timing, infra, domain constraints).
- When a production incident happens, add a guardrail line to project rule immediately.

## 4) Copy/paste checklist
- [ ] Rule file path is `.cursor/rules/*.mdc`
- [ ] Frontmatter exists (`description`, `alwaysApply`)
- [ ] Core safety rules are short and explicit
- [ ] Rule references real symbols/files in this repo
