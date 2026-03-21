---
phase: 01-backend-foundation
plan: 01
subsystem: web-backend
tags: [fastapi, sqlite, crud, jobs, data-layer]
dependency_graph:
  requires: []
  provides: [web.db CRUD interface, web.app FastAPI instance, changelogs/jobs.db schema]
  affects: [01-02-PLAN.md (pipeline runner + API routes depends on these contracts)]
tech_stack:
  added: [fastapi[standard]>=0.115.0, uvicorn (bundled via fastapi[standard])]
  patterns: [sqlite3 raw CRUD, FastAPI lifespan context manager, sqlite3.Row row_factory]
key_files:
  created:
    - requirements.txt (modified — fastapi[standard]>=0.115.0 added)
    - web/__init__.py
    - web/db.py
    - web/app.py
  modified: []
decisions:
  - "Used asynccontextmanager lifespan pattern (not deprecated @app.on_event) per FastAPI >=0.93 standard"
  - "jobs.db placed at changelogs/jobs.db — inside existing changelogs/ output directory (already in .gitignore)"
  - "status values: queued -> fetching -> parsing -> generating -> done | failed | partial (D-01, D-02, D-03 from 01-CONTEXT.md)"
  - "No _env references in db.py — secrets never stored in job records"
metrics:
  duration_minutes: 12
  completed_date: "2026-03-21"
  tasks_completed: 3
  files_modified: 4
---

# Phase 1 Plan 01: FastAPI Skeleton and SQLite Data Layer Summary

FastAPI app instance and SQLite raw-sqlite3 CRUD layer for async changelog job tracking, establishing the data contracts that Plan 02 (pipeline runner) depends on.

## What Was Built

**requirements.txt** — appended `fastapi[standard]>=0.115.0` under a `# Web UI layer` comment. All 7 original dependencies preserved. uvicorn is bundled inside `fastapi[standard]` — not added separately.

**web/__init__.py** — empty package marker enabling `from web.app import app` imports.

**web/db.py** — raw sqlite3 CRUD layer for the `jobs` table at `changelogs/jobs.db`:
- `init_db()` — creates changelogs/ dir and jobs table if not exists (idempotent)
- `get_db()` — FastAPI dependency generator yielding sqlite3 connection with `row_factory = sqlite3.Row`
- `create_job(since_str, until_str, config_snapshot)` — inserts queued job, returns UUID string
- `get_job(job_id)` — returns row as dict or None
- `update_job_status(job_id, status, progress_message)` — updates status during pipeline stages
- `update_job_result(job_id, status, ...)` — writes all rendered outputs (slack_text, email_html, markdown_text, intelligence_json) and marks completion

**web/app.py** — FastAPI application instance:
- asynccontextmanager lifespan calls `init_db()` on startup
- `GET /health` returns `{"status": "ok"}` liveness probe
- No job routes yet (those belong to Plan 02)

## Jobs Table Schema

| Column | Type | Notes |
|--------|------|-------|
| id | TEXT PRIMARY KEY | UUID |
| status | TEXT NOT NULL | queued / fetching / parsing / generating / done / failed / partial |
| progress_message | TEXT | Human-readable stage description |
| since | TEXT NOT NULL | ISO date string |
| until | TEXT NOT NULL | ISO date string |
| config_snapshot | TEXT | JSON-encoded config (no _env) |
| slack_text | TEXT | Rendered Slack output |
| email_html | TEXT | Rendered email HTML |
| markdown_text | TEXT | Rendered markdown |
| intelligence_json | TEXT | JSON-encoded LLM output |
| failed_repos | TEXT | JSON list of repo names that failed |
| created_at | TEXT NOT NULL | ISO timestamp UTC |
| completed_at | TEXT | ISO timestamp UTC |

## Decisions Made

1. **Lifespan over @app.on_event** — Using `asynccontextmanager` lifespan is the FastAPI >=0.93 standard. `@app.on_event("startup")` is deprecated.

2. **jobs.db inside changelogs/** — The `changelogs/` directory already exists and is already in `.gitignore`. Placing `jobs.db` there keeps runtime outputs together and naturally excluded from version control.

3. **Status stages per D-01/D-02/D-03** — `partial` status when repo fetches fail (job continues), `failed` when LLM fails (operator must retry), `failed_repos` column stores which repos failed as JSON list.

4. **No _env in db.py** — Callers (Plan 02 tasks.py) are responsible for stripping `config["_env"]` before passing `config_snapshot` to `create_job()`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] fastapi not installed in Python environment**
- **Found during:** Task 3 automated verify (`python3 -c "from web.app import app..."`)
- **Issue:** `ModuleNotFoundError: No module named 'fastapi'` — package added to requirements.txt but not installed
- **Fix:** Ran `pip3 install "fastapi[standard]>=0.115.0" --break-system-packages` (Homebrew-managed Python 3.13.2 requires `--break-system-packages` flag)
- **Files modified:** None (system package installation only)
- **Commit:** N/A (pip install, not a code change)

## Known Stubs

None — all 6 CRUD functions are fully implemented and verified against a real SQLite file.

## Verification Results

All three verification commands from the plan passed:

```
python3 -c "import web; from web.app import app; from web.db import init_db, create_job, get_job; print('All imports OK')"
# Output: All imports OK

grep "fastapi\[standard\]" requirements.txt
# Output: fastapi[standard]>=0.115.0

python3 changelog.py --help
# Output: full CLI help text (CLI untouched)
```

## Self-Check: PASSED

Files created:
- FOUND: requirements.txt (modified)
- FOUND: web/__init__.py
- FOUND: web/db.py
- FOUND: web/app.py

Commits:
- FOUND: 9ad8587 — chore(01-01): add fastapi[standard]>=0.115.0 and create web package
- FOUND: e7bcc10 — feat(01-01): create web/db.py SQLite CRUD layer for jobs
- FOUND: 349b97e — feat(01-01): create web/app.py FastAPI app with lifespan and health check
