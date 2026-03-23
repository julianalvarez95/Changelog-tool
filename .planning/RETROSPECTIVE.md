# Retrospective

## Milestone: v1.0 — MVP

**Shipped:** 2026-03-23
**Phases:** 3 | **Plans:** 2 formal | **Commits:** 21

### What Was Built

- Async SQLite job engine (Phase 1) — non-blocking pipeline execution with stage-level progress
- Complete operator web UI (Phase 2) — configure, generate, send with per-channel results
- History browser (Phase 3) — browse and view all past changelog runs

### What Worked

- Phase 1 followed full GSD workflow (CONTEXT → PLAN → EXECUTE → VERIFY) — resulted in clean, well-documented code with zero regressions
- Vanilla JS + Tailwind CDN decision kept the frontend deployable without any toolchain setup
- Wrapping the existing CLI rather than rewriting it preserved all distribution logic and kept Phase 1 focused

### What Was Inefficient

- Phases 2 & 3 were shipped in a single commit without GSD artifacts (PLAN.md, SUMMARY.md, VERIFICATION.md) — this made the milestone audit harder and left 7/9 requirements formally unverified
- The `failed_repos` deserialization bug shipped undetected because there was no VERIFICATION.md for Phase 2/3 — caught only during milestone audit
- REQUIREMENTS.md traceability table never updated after Phases 2 & 3 completed — required manual reconciliation during audit

### Patterns Established

- The GSD verification step (VERIFICATION.md) caught a subtle security decision (`_env` never persisted) that might have been missed otherwise
- Integration checker correctly identified the `failed_repos` deserialization bug and the unused `db=Depends(get_db)` dependency
- Running the audit before archiving was worth it — found a real bug

### Key Lessons

- When shipping phases without formal PLAN.md files, at minimum create a SUMMARY.md and update the requirements traceability table — the artifact gap is what caused the audit `gaps_found` status, not missing functionality
- For a 3-phase milestone this size, the GSD planning overhead (CONTEXT → PLAN → verify) is right-sized for Phase 1; phases that are tightly coupled to a large frontend benefit from at least a lightweight PLAN.md
- The `failed_repos` bug pattern (store as JSON string, forget to deserialize) is easy to introduce with SQLite raw dictionaries — consider a helper that deserializes all JSON columns on read

### Cost Observations

- Sessions: ~2
- Notable: Phase 1 full GSD workflow took the same time as Phases 2 & 3 combined (shipped together), suggesting GSD overhead was proportional

## Cross-Milestone Trends

*(First milestone — baseline established)*

| Metric | v1.0 |
|--------|------|
| Phases | 3 |
| Days | 5 |
| Files changed | 31 |
| Lines added | +5,694 |
| Bugs found in audit | 1 (functional) |
| Artifact gap phases | 2/3 |
