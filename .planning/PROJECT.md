# Changelog Tool UI

## What This Is

A web UI layer on top of the existing changelog-tool CLI. Internal operators (technical and non-technical) use it to configure, generate, preview, and distribute changelogs to stakeholders — without touching the command line. The bigger vision is a stakeholder portal where stakeholders read changelogs directly in the app.

## Core Value

Non-technical operators can generate and send polished changelogs from multiple repos without ever opening a terminal.

## Requirements

### Validated

- [x] User can trigger changelog generation — Validated in Phase 1: Backend Foundation (async job API)
- [x] User can observe async progress during generation — Validated in Phase 1: Backend Foundation (GET /jobs/{id} status polling)

### Active

- [ ] User can configure date range for changelog generation
- [ ] User can select distribution target (Slack channel, email list)
- [ ] User can configure tone/format (technical detail level)
- [ ] User can trigger changelog generation
- [ ] User can preview the generated changelog before sending
- [ ] User can send the changelog to configured distribution targets
- [ ] User can browse a history of past generated changelogs
- [ ] Admin can configure repos and API tokens through the UI

### Out of Scope

- User authentication / login — internal tool, deferred to later
- Stakeholder portal (read-only view for stakeholders) — v2 vision, not v1
- Scheduling / recurring changelogs — not in initial scope

## Current State

Phase 1 complete — Async job engine, SQLite schema, and job API endpoints (POST /jobs, GET /jobs/{id}, GET /jobs/{id}/result) are live. FastAPI app runs via `uvicorn web.app:app`. CLI unchanged.

## Context

- The CLI tool is already fully built and working (`changelog.py` entry point)
- It fetches commits from GitHub and Bitbucket via API tokens
- Uses OpenAI to generate structured summaries, falls back to raw parsed commits
- Distributes via Slack SDK and Gmail SMTP
- Config lives in `config.yaml` (repos, categories, LLM settings) and `.env` (secrets)
- The UI will wrap the existing Python pipeline — not replace it
- Admin-configured repos and tokens are set once; operators pick from that pool

## Constraints

- **Tech stack**: Must integrate with existing Python CLI pipeline
- **Auth**: No authentication in v1 — internal tool assumption
- **Existing CLI**: Must stay functional; UI is an additive layer, not a replacement

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| No auth in v1 | Internal tool, reduces scope significantly | — Pending |
| UI wraps existing CLI | Existing pipeline is solid, no need to rewrite | — Pending |

---

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd:transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-03-21 after Phase 1 completion*
