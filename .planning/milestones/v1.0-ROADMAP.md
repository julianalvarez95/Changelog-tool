# Roadmap: Changelog Tool UI

## Overview

Three phases deliver a web UI layer over the existing Python CLI pipeline. Phase 1 builds the async job engine and SQLite foundation that everything else depends on. Phase 2 delivers the full operator workflow: configure, generate, and send changelogs without touching the CLI. Phase 3 adds history browsing so operators can reference and verify past distributions.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Backend Foundation** - Async job engine, SQLite schema, and polling endpoint that enable non-blocking pipeline execution (completed 2026-03-21)
- [x] **Phase 2: Operator Workflow** - Full configure → generate → send flow accessible from the web UI (completed 2026-03-22)
- [x] **Phase 3: History** - Browse and view all past generated changelogs (completed 2026-03-22)

## Phase Details

### Phase 1: Backend Foundation
**Goal**: The changelog pipeline runs asynchronously from an HTTP request, job status is queryable, and results are persisted — without blocking the web server
**Depends on**: Nothing (first phase)
**Requirements**: GENR-04, GENR-05
**Success Criteria** (what must be TRUE):
  1. Posting a job request to the API returns a job ID immediately (no waiting for pipeline completion)
  2. Polling the job status endpoint returns the current pipeline stage (fetching, parsing, generating, done, failed)
  3. A completed job's rendered output is retrievable via the job ID
  4. The existing CLI (`python3 changelog.py`) still runs independently and produces correct output
**Plans**: 2 plans

Plans:
- [x] 01-01-PLAN.md — SQLite data layer + FastAPI app skeleton (requirements.txt, web/db.py, web/app.py)
- [x] 01-02-PLAN.md — Pipeline background runner + job API endpoints (web/tasks.py, web/routes/jobs.py)

### Phase 2: Operator Workflow
**Goal**: A non-technical operator can open the web UI, configure a changelog run, generate it, and send it to distribution targets — end to end, without the CLI
**Depends on**: Phase 1
**Requirements**: GENR-01, GENR-02, GENR-03, GENR-06, GENR-07
**Success Criteria** (what must be TRUE):
  1. Operator can set a date range (or use "since last run") and select distribution targets before generating
  2. Operator can select tone/format level (e.g., technical vs. summary) before generating
  3. The UI shows live progress feedback while the pipeline runs (5–30 seconds), not a blank spinner
  4. Operator can send the generated changelog to each selected channel individually and sees a success or failure result per channel
**Plans**: TBD

### Phase 3: History
**Goal**: Operators can browse all past changelog runs and open any entry to read its content — without re-running generation
**Depends on**: Phase 2
**Requirements**: HIST-01, HIST-02
**Success Criteria** (what must be TRUE):
  1. Operator can see a list of all past changelog runs with date range and send status visible at a glance
  2. Operator can open any past entry and read the full rendered changelog content
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Backend Foundation | 2/2 | Complete   | 2026-03-21 |
| 2. Operator Workflow | 2/2 | Complete | 2026-03-22 |
| 3. History | 1/1 | Complete | 2026-03-22 |
