# Phase 1: Backend Foundation - Context

**Gathered:** 2026-03-21
**Status:** Ready for planning

<domain>
## Phase Boundary

Build the FastAPI + SQLite async job engine. Accept job requests via HTTP, run the changelog pipeline in a background thread (non-blocking), persist results, and expose a polling endpoint for job status. No UI in this phase — pure API layer. The existing CLI (`python3 changelog.py`) must remain fully functional and unchanged.

</domain>

<decisions>
## Implementation Decisions

### Partial Failure — Repo Fetch

- **D-01:** If one or more repo fetches fail (bad token, network error), the job continues with the repos that succeeded.
- **D-02:** Job status shows `partial` (not `done`) when any repo failed. The failed repo names and errors are logged in the job record so Phase 2 UI can surface them prominently.

### Partial Failure — LLM

- **D-03:** If the OpenAI call fails (timeout, quota, bad key), the job fails entirely. No fallback to raw commits — operator must retry.

### Claude's Discretion

- **Job status stages:** Claude decides the status granularity. Recommendation from research: use per-pipeline-stage reporting (`queued` → `fetching` → `parsing` → `generating` → `done` / `failed` / `partial`). This gives Phase 2 meaningful progress to display.
- **Output storage:** Claude decides what to persist per job. Recommendation: store all 3 rendered outputs (`slack_text`, `email_html`, `markdown_text`) in SQLite so Phase 2 send flow reads from storage rather than re-rendering.
- **last_run.json update policy:** Claude decides. Recommendation: web-triggered jobs update `last_run.json` (same file the CLI uses) so "since last run" stays consistent across both entry points.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project requirements
- `.planning/REQUIREMENTS.md` — v1 requirements; GENR-04 and GENR-05 are Phase 1's scope
- `.planning/PROJECT.md` — Core constraints: no auth in v1, existing CLI must stay functional, UI is additive

### Existing pipeline (direct import targets)
- `changelog.py` — Entry point; shows full pipeline orchestration flow and `last_run.json` read/write logic
- `src/config.py` — `load_config()` signature; note `_inject_env_secrets()` builds `config["_env"]` with all 7 credentials — **never serialize this dict in API responses**
- `src/llm.py` — `generate_intelligence()` is the slow step (5–30s, no timeout set); must run in executor thread, not async coroutine
- `src/generator.py` — `render()` signature for producing slack/email/markdown outputs

### Research findings
- `.planning/research/ARCHITECTURE.md` — Direct import pattern, FastAPI BackgroundTasks, SQLite schema recommendations
- `.planning/research/PITFALLS.md` — Blocking HTTP thread (pitfall #1), secrets leakage via config API (pitfall #2), duplicate distribution (pitfall #3), .env vs config.yaml split (pitfall #4)
- `.planning/research/STACK.md` — FastAPI `>=0.115`, uvicorn, SQLite via stdlib `sqlite3`; no Celery/Redis

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/config.py:load_config()` — Can be imported directly into the web layer. Already handles `.env` loading and config.yaml parsing. Note: anchored to project root via `__file__` path resolution.
- `src/llm.py:generate_intelligence(all_categorized, config, since, until)` — Direct import. Synchronous; wrap in `run_in_executor` with ThreadPoolExecutor.
- `src/generator.py:render(categorized, config, since, until, template, intelligence)` — Direct import. Returns rendered string per template.
- `src/parser.py:categorize_commits()` — Direct import. Fast, synchronous, safe.
- `src/fetchers/github.py` + `src/fetchers/bitbucket.py` — Direct import. Blocking network calls; already parallelized with ThreadPoolExecutor in `changelog.py`.

### Established Patterns
- **Synchronous throughout:** All `src/` code is synchronous. Wrap the entire pipeline in `run_in_executor` — do not try to make individual steps async.
- **ThreadPoolExecutor for repo fetches:** `changelog.py` already parallelizes fetches. The web runner can reuse this pattern inside the executor thread.
- **config["_env"] for secrets:** All credentials live under `config["_env"]`. This key must be stripped from any API response.

### Integration Points
- `web/app.py` (new) imports from `src/config`, `src/llm`, `src/generator`, `src/parser`, `src/fetchers/*`
- `web/db.py` (new) creates and manages `./changelogs/jobs.db` SQLite file
- `web/tasks.py` (new) contains the async job runner function
- `last_run.json` in project root — web runner reads and writes same file as CLI

</code_context>

<specifics>
## Specific Ideas

No specific references or "I want it like X" moments — open to standard FastAPI + SQLite patterns from the research.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 01-backend-foundation*
*Context gathered: 2026-03-21*
