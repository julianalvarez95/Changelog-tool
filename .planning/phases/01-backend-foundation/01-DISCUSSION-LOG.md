# Phase 1: Backend Foundation - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-21
**Phase:** 01-backend-foundation
**Areas discussed:** Partial failure behavior

---

## Partial Failure — Repo Fetch

| Option | Description | Selected |
|--------|-------------|----------|
| Continue with available repos | Job succeeds with whatever repos worked. Error logged in job record. | |
| Fail the whole job | Any repo failure = job failed. Operator must retry. | |
| Continue + surface prominently | Job completes but status shows 'partial' — error visible in UI | ✓ |

**User's choice:** Continue + surface prominently
**Notes:** Job status = `partial` when any repo failed. Errors logged in job record for Phase 2 UI to display.

---

## Partial Failure — LLM

| Option | Description | Selected |
|--------|-------------|----------|
| Fall back to raw commits | Same as CLI --no-llm mode — changelog still generated, less polished | |
| Fail the job | No LLM = no changelog. Operator retries. | ✓ |

**User's choice:** Fail the job
**Notes:** LLM failure is a hard failure — no fallback to raw commits.

---

## Claude's Discretion

- Job progress stages — Claude picks granularity (recommendation: per-pipeline-stage)
- Output storage scope — Claude picks what to persist (recommendation: all 3 rendered formats)
- last_run.json update policy — Claude picks (recommendation: shared with CLI)

## Deferred Ideas

None.
