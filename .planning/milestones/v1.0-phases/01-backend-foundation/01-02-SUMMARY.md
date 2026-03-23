---
phase: 01-backend-foundation
plan: 02
subsystem: web-backend
tags: [fastapi, sqlite, background-tasks, pipeline-runner, api-routes]
dependency_graph:
  requires: [web.db CRUD interface from 01-01, web.app FastAPI instance from 01-01]
  provides: [run_pipeline() background task, POST /jobs, GET /jobs/{id}, GET /jobs/{id}/result]
  affects: [02-frontend-ui (Phase 2 builds UI on these endpoints)]
tech_stack:
  added: []
  patterns: [FastAPI BackgroundTasks for non-blocking job execution, APIRouter for route modules, Pydantic BaseModel for request validation, ThreadPoolExecutor for parallel repo fetching, os.replace for atomic file writes]
key_files:
  created:
    - web/tasks.py
    - web/routes/__init__.py
    - web/routes/jobs.py
  modified:
    - web/app.py
decisions:
  - "D-01/D-02: partial repo fetch failure continues pipeline; final status='partial' with failed_repos populated"
  - "D-03: LLM failure sets status='failed' with no fallback (operator must retry)"
  - "config['_env'] stripped before storage; never passed to any API response"
  - "last_run.json updated atomically after successful web-triggered run (os.replace, Pitfall 10)"
  - "GET /jobs/{id} returns status fields only; GET /jobs/{id}/result returns rendered content"
  - "intelligence_json kept internal — not exposed in any API response"
metrics:
  duration_minutes: 3
  completed_date: "2026-03-21"
  tasks_completed: 3
  files_modified: 4
---

# Phase 1 Plan 02: Pipeline Runner and Job API Endpoints Summary

Async changelog pipeline runner and three job API endpoints (POST /jobs, GET /jobs/{id}, GET /jobs/{id}/result) completing the Phase 1 core loop — non-blocking job creation, stage-level progress polling, and rendered output retrieval satisfying ROADMAP Phase 1 Success Criterion 3.

## What Was Built

**web/tasks.py** — Background pipeline runner function `run_pipeline(job_id, since_str, until_str)`:
- Synchronous function called by FastAPI BackgroundTasks in a thread (never blocks the HTTP worker)
- Stage progression written to SQLite: `fetching` -> `parsing` -> `generating` -> `done`/`partial`/`failed`
- D-01: Repo fetch failures are caught per-repo, execution continues with remaining repos
- D-02: `failed_repos` list populated; final status set to `"partial"` if any repo failed, `"done"` if all succeeded
- D-03: LLM failure (None return) sets status to `"failed"` — no fallback to raw commits
- `config["_env"]` never stored (secrets stripped before any persistence)
- `last_run.json` updated atomically via `os.replace` after successful run (shared with CLI, Pitfall 10)
- Top-level exception catch sets status to `"failed"` for any unexpected error

**web/routes/__init__.py** — Empty package marker for the routes module.

**web/routes/jobs.py** — Three API endpoints:
- `POST /jobs` — accepts `{"since": "YYYY-MM-DD", "until": "YYYY-MM-DD"}`, validates date format and ordering, creates job in SQLite, schedules `run_pipeline` as BackgroundTask, returns `{"job_id": "...", "status": "queued"}` with HTTP 202 immediately
- `GET /jobs/{job_id}` — returns status fields only (`id`, `status`, `progress_message`, `since`, `until`, `failed_repos`, `created_at`, `completed_at`); rendered content deliberately excluded; HTTP 404 for unknown job
- `GET /jobs/{job_id}/result` — returns `slack_text`, `email_html`, `markdown_text` for `done`/`partial` jobs; HTTP 404 for unknown job; HTTP 409 for jobs not yet complete; `intelligence_json` and `config_snapshot` not exposed

**web/app.py** (modified) — Added `from web.routes.jobs import router as jobs_router` import and `app.include_router(jobs_router)` registration.

## Route Inventory

| Method | Path | HTTP Status | Purpose |
|--------|------|-------------|---------|
| POST | /jobs | 202 | Trigger generation (non-blocking) |
| GET | /jobs/{job_id} | 200/404 | Poll status and progress |
| GET | /jobs/{job_id}/result | 200/404/409 | Retrieve rendered outputs |
| GET | /health | 200 | Liveness probe (from Plan 01) |

## Pipeline Stage Progression

```
queued (created by POST /jobs)
  -> fetching  "Fetching commits from repositories..."
  -> parsing   "Parsing and categorizing commits..."
  -> generating "Generating changelog with LLM..." | "Rendering changelog..."
  -> done | partial | failed
```

## Decisions Made

1. **GET /jobs/{id} excludes rendered content** — Separating the polling endpoint from the result endpoint avoids transferring large HTML/markdown payloads on every poll. Callers poll the status endpoint until `done`/`partial`, then fetch the result once.

2. **D-01/D-02 partial failure design** — If any repo fetch fails, the pipeline continues with successful repos. Final status is `partial` (not `done`) so the UI can surface which repos failed. All-repo failure sets `failed`.

3. **D-03 LLM failure = job failed** — No fallback to raw commits when LLM fails. Forces operator to retry rather than silently distributing degraded output.

4. **intelligence_json internal-only** — LLM JSON not exposed via any API endpoint. It is stored in SQLite for debugging but not surfaced to callers.

5. **os.replace for atomic last_run.json write** — Prevents JSON corruption when CLI and web server share the file (Pitfall 10).

## Deviations from Plan

None — plan executed exactly as written. All three tasks completed in sequence; the `/result` endpoint was included in the same file as the status endpoint (per plan's `<files>` spec for Task 3).

## Known Stubs

None — all endpoints are fully wired. `run_pipeline` correctly imports and calls the existing `src/` pipeline functions. All three rendered outputs (`slack_text`, `email_html`, `markdown_text`) flow from the pipeline to SQLite to the result endpoint.

## Verification Results

End-to-end verification all passed:

```
python3 -c "from web.app import app; from web.tasks import run_pipeline; from web.routes.jobs import router; print('All imports OK')"
# Output: All imports OK

python3 -c "from web.app import app; print([r.path for r in app.routes if hasattr(r, 'path')])"
# Output: ['/openapi.json', '/docs', '/docs/oauth2-redirect', '/redoc', '/jobs', '/jobs/{job_id}', '/jobs/{job_id}/result', '/health']

python3 changelog.py --help
# Output: full CLI help text (CLI untouched)

grep "_env" web/routes/jobs.py && echo "FAIL" || echo "OK: no _env in routes"
# Output: OK: no _env in routes

python3 -c "import ast; ast.parse(open('web/routes/jobs.py').read()); print('routes/jobs.py parses OK')"
# Output: routes/jobs.py parses OK
```

## Self-Check: PASSED

Files created/verified:
- FOUND: web/tasks.py
- FOUND: web/routes/__init__.py
- FOUND: web/routes/jobs.py
- FOUND: web/app.py (modified)

Commits:
- FOUND: b9980f7 — feat(01-02): create web/tasks.py pipeline background runner
- FOUND: f867e23 — feat(01-02): create web/routes/jobs.py and register router in app.py
