---
description: Record what this session did so the next agent can pick up from here
---

Write a handoff for this session (this repo only; the sibling repo has its own docs).

1. Review what changed: `git status`, `git diff` (and `git diff --staged`), and re-read the conversation.
2. Write `docs/progress/log/<YYYY-MM-DD>-<topic>.md` with these sections:
   - **What was done** (with links to the files)
   - **Decisions** (and who made them: owner or agent)
   - **Not done / next steps**
   - **How to verify** (exact commands)
3. Update `docs/progress/STATUS.md` to the current state only: move finished items to Done, add new todos and known issues, bump "Last updated".
4. Update any doc whose described behaviour changed (`CLAUDE.md`, `docs/**`). For each new decision made with the owner, add an ADR in `docs/decisions/` and its row in `docs/decisions/README.md`. If the change affects the sibling repo (e.g. an API contract change), say so in the log and in the summary.
5. Don't commit. Summarize the handoff to the owner in 3–5 lines.
