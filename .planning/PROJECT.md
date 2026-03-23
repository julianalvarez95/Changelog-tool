# Changelog Tool UI

## What This Is

A web UI layer on top of the existing changelog-tool CLI. Internal operators (technical and non-technical) use it to configure, generate, and distribute changelogs to Slack and email — without touching the command line. v1.0 shipped the complete configure → generate → send → history loop. The bigger vision is a stakeholder portal where stakeholders read changelogs directly in the app.

## Core Value

Non-technical operators can generate and send polished changelogs from multiple repos without ever opening a terminal.

## Requirements

### Validated

- ✓ User can trigger changelog generation from the UI — v1.0 (POST /jobs, async 202 response)
- ✓ User sees async generation progress while the pipeline runs — v1.0 (GET /jobs/{id} polling, stage-level messages)
- ✓ User can select a date range (from/until) before generating — v1.0 (date inputs wired to POST /jobs)
- ✓ User can select distribution targets before generating — v1.0 (checkboxes from GET /config → POST /jobs/{id}/send)
- ✓ User can configure tone/format before generating — v1.0 (tone radio → run_pipeline tone_override)
- ✓ User can send the generated changelog to selected distribution targets — v1.0 (POST /jobs/{id}/send → Slack + email)
- ✓ User sees per-channel send result (success or failure) — v1.0 (per-target success/error rendered inline)
- ✓ User can browse an archive of all past generated changelogs — v1.0 (GET /jobs list, history tab)
- ✓ User can open a past changelog entry and view its content — v1.0 (GET /jobs/{id}/result, history detail view)

### Active

*(None — all v1 requirements validated. New requirements defined for next milestone.)*

### Out of Scope

- User authentication / login — internal tool, deferred to later
- Stakeholder portal (read-only view for stakeholders) — v2 vision, not v1
- Scheduling / recurring changelogs — not in initial scope
- Preview before send — opted for generate → send direct flow; revisit in v2
- Admin config management — config stays in config.yaml + .env; reduces attack surface
- Inline changelog editing — undermines automation value; deliberate exclusion

## Current State

v1.0 shipped. Full operator workflow is live:
- FastAPI app serves the web UI from `web/static/index.html`
- Run: `uvicorn web.app:app --reload --host 0.0.0.0 --port 8000`
- CLI (`python3 changelog.py`) unchanged and fully functional
- Database: `changelogs/jobs.db` (SQLite, auto-created on startup)
- ~5,700 LOC added across 31 files
- Tech stack: FastAPI + vanilla JS + Tailwind CDN + SQLite

**Known tech debt (v1.0):**
- Phases 2 & 3 shipped without formal GSD verification artifacts (no PLAN.md / SUMMARY.md / VERIFICATION.md)
- No VALIDATION.md (Nyquist) for any phase
- `config_snapshot` column always NULL (wired but unused)
- GET /config failure hides distribution targets silently (no user error message)

## Context

- The CLI tool is already fully built and working (`changelog.py` entry point)
- It fetches commits from GitHub and Bitbucket via API tokens
- Uses OpenAI to generate structured summaries, falls back to raw parsed commits
- Distributes via Slack SDK and Gmail SMTP
- Config lives in `config.yaml` (repos, categories, LLM settings) and `.env` (secrets)
- The UI wraps the existing Python pipeline — not replacing it
- Admin-configured repos and tokens are set once; operators pick from that pool

## Constraints

- **Tech stack**: Must integrate with existing Python CLI pipeline
- **Auth**: No authentication in v1 — internal tool assumption
- **Existing CLI**: Must stay functional; UI is an additive layer, not a replacement

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| No auth in v1 | Internal tool, reduces scope significantly | ✓ Good — shipped faster |
| UI wraps existing CLI via direct import | Existing pipeline is solid, no need to rewrite | ✓ Good — no regressions |
| Vanilla JS + Tailwind CDN (no build step) | Deployable without toolchain, fast to iterate | ✓ Good — kept it simple |
| Phases 2 & 3 shipped in one commit | Expedited delivery, accepted artifact gap | ⚠ Revisit — missed verification artifacts |
| SQLite for job persistence | Simple, no infra, zero config | ✓ Good — right tool for internal tool |
| `config_snapshot` column reserved but unused | Future option for per-job config snapshots | — Pending — may drop in v2 |

---

*Last updated: 2026-03-23 after v1.0 milestone*
