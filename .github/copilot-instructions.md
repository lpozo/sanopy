# Copilot Workspace Instructions for Sanopy

## Read [AGENTS.md](../AGENTS.md) first

**[AGENTS.md](../AGENTS.md) is the single source of truth** for this
repository: scope, commands, architecture, non-obvious behavior, and
conventions all live there. Read it before making changes, and follow it.

This file intentionally does **not** restate that content. An earlier
version did, and it drifted badly out of date — it was still describing a
linter-invocation strategy that had been replaced. If anything here ever
appears to conflict with AGENTS.md, **AGENTS.md wins**; treat the
conflict as a bug in this file and fix it.

What AGENTS.md covers, and where to look:

| Question | Section in AGENTS.md |
| --- | --- |
| What is in and out of scope for this repo? | intro (**Scope**) |
| How do I install deps, test, lint, type-check, self-scan? | Commands |
| Where does each module live and what owns what? | Architecture |
| Exit codes, stdout vs stderr, linter resolution, config rules | Non-obvious behavior |
| Commit style, docs-in-step rule, typing bar, test policy | Conventions |
| What do README, CHANGELOG, and pyproject.toml each cover? | Documentation |

## Working agreement

- **Don't duplicate guidance into this file.** Add it to AGENTS.md and,
  if it needs signposting, add a row to the table above.
