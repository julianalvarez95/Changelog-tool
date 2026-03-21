# Architecture Patterns

**Domain:** Web UI wrapping an existing Python CLI pipeline
**Researched:** 2026-03-21
**Confidence:** HIGH (based on direct codebase analysis + established Python web framework patterns)

---

## Recommended Architecture

**Monolith: FastAPI serving a lightweight frontend (htmx or React), with in-process pipeline invocation and SQLite for job history.**

This is not a microservices problem. The pipeline is already modular (fetchers → parser → LLM → postprocessor → generator → distributors). The web layer should call those same Python functions directly — not shell out to the CLI. No message queue, no separate worker process, no Redis. An internal tool with <10 concurrent users does not need distributed infrastructure.

```
Browser
  │
  ├── GET /  (dashboard)
  ├── POST /jobs  (trigger generation)
  ├── GET /jobs/{id}  (poll status)
  ├── GET /jobs/{id}/preview  (rendered output)
  ├── POST /jobs/{id}/send  (distribute)
  └── GET/PUT /config  (admin config)
  │
FastAPI app (web/app.py)
  │
  ├── Background Tasks (FastAPI BackgroundTasks or asyncio.create_task)
  │     Runs the pipeline in a thread: load_config → fetch → parse → LLM → postprocess → render
  │     Writes result to SQLite on completion
  │
  ├── SQLite (jobs.db via SQLAlchemy or raw sqlite3)
  │     jobs table: id, status, since, until, config_snapshot, rendered_slack, rendered_email,
  │                  rendered_markdown, intelligence_json, created_at, completed_at, sent_at
  │
  ├── src/ (EXISTING, UNCHANGED)
  │     fetchers/github.py, fetchers/bitbucket.py
  │     parser.py
  │     llm.py
  │     postprocessor.py
  │     generator.py
  │     distributors/slack.py, distributors/email.py
  │     config.py
  │
  └── Config storage
        config.yaml (existing, still the source of truth for CLI use)
        .env (existing, still holds secrets)
        Web UI reads and writes config.yaml + .env directly for admin management
```

---

## Component Boundaries

| Component | Responsibility | Communicates With |
|-----------|---------------|-------------------|
| FastAPI app | HTTP routing, request/response, job lifecycle | Browser, Background Tasks, SQLite, src/ |
| Background Task runner | Executes pipeline in a thread pool | src/ modules (direct import), SQLite |
| SQLite (jobs.db) | Persists job records, rendered outputs, status | FastAPI app, Background Tasks |
| src/ pipeline (existing) | Fetch, parse, LLM, render, distribute | External APIs (GitHub, Bitbucket, OpenAI, Slack, Gmail) |
| Config layer (web) | Read/write config.yaml and .env via web forms | FastAPI app, src/config.py |
| Frontend (htmx or React) | UI rendering, polling for job status, form submission | FastAPI app (HTTP) |

**Boundary rules:**
- The web layer NEVER calls `subprocess` or shells out to `changelog.py`. It imports and calls `src/` functions directly.
- The existing `changelog.py` CLI entry point remains untouched and independently functional.
- `src/config.py` is used as-is by both CLI and web app. The web admin config editor reads/writes `config.yaml` and `.env` directly via file I/O.
- Distribution (Slack send, email send) happens as a separate, explicit web action AFTER preview — never automatically on job completion.

---

## Data Flow

### Job Execution Flow

```
1. User submits form: {since, until, tone, dry_run}
   POST /jobs → FastAPI creates job record in SQLite (status: "pending")
   → Returns job_id to browser

2. FastAPI spawns background task (thread)
   → load_config() from config.yaml + .env
   → fetch_repo_commits() for each repo (parallel, ThreadPoolExecutor — existing behavior)
   → categorize_commits() per repo
   → generate_intelligence() (OpenAI call, or cache hit)
   → validate_and_clean()
   → render() for each template (slack.j2, email.html.j2, markdown.md.j2)
   → Write rendered outputs + intelligence to SQLite (status: "complete")

3. Browser polls GET /jobs/{id} every 2s
   → Returns {status, progress_message} until complete
   → On complete: redirect to GET /jobs/{id}/preview

4. User reviews preview (rendered HTML, Slack text, Markdown)
   → Optionally edits nothing (preview is read-only in v1)
   → Clicks "Send to Slack" → POST /jobs/{id}/send?channel=slack
   → Clicks "Send via Email" → POST /jobs/{id}/send?channel=email
   → Each send action calls the appropriate distributor from src/distributors/
   → Updates SQLite job record with sent_at and channels_sent
```

### Config Management Flow

```
1. Admin opens /config
   → FastAPI reads config.yaml via yaml.safe_load()
   → Reads .env via python-dotenv or raw file parse
   → Renders form pre-filled with current values

2. Admin submits changes
   PUT /config → FastAPI validates fields → writes config.yaml via yaml.dump()
   → writes .env (overwrite specific keys, preserve others)
   → Returns success or validation errors

3. Secrets (API tokens) are stored ONLY in .env, never in SQLite or returned to browser.
   Config form shows masked values ("••••••" + last 4 chars) for existing secrets.
```

### History Flow

```
GET /history → queries SQLite jobs table, ordered by created_at DESC
→ Returns list: {id, period, status, sent_at, channels_sent, commit_count}
→ Each row links to GET /jobs/{id}/preview (re-displays stored rendered output)
```

---

## Patterns to Follow

### Pattern 1: Direct Module Import (not subprocess)

**What:** Call `src/` Python functions directly from FastAPI routes/background tasks. Same process, no shell fork.

**When:** Always. This is the only correct approach for a same-language web wrapper.

**Why:** subprocess adds complexity, encoding issues, and no real benefit. The src/ modules are already importable. `load_config()`, `categorize_commits()`, `generate_intelligence()`, `render()`, and the distributor `send()` functions all have clean, callable signatures.

**Example:**
```python
# web/tasks.py
from src.config import load_config
from src.parser import categorize_commits
from src.llm import generate_intelligence
from src.postprocessor import validate_and_clean
from src.generator import render

def run_pipeline(job_id: str, since: datetime, until: datetime, db):
    config = load_config()
    # ... same logic as changelog.py main(), but writing results to db
    db.update_job(job_id, status="complete", slack_text=slack_text, ...)
```

### Pattern 2: Thread-Based Background Tasks (not async workers)

**What:** Run the pipeline in a thread via `fastapi.BackgroundTasks` or `asyncio.loop.run_in_executor`. Do NOT use Celery, RQ, or a separate worker process.

**When:** For this scale (internal tool, rare concurrent runs). Background tasks are sufficient.

**Why:** The pipeline involves blocking I/O (GitHub API, Bitbucket API, OpenAI API). These are already handled synchronously in `src/` with `ThreadPoolExecutor` for parallel fetches. Wrapping in a FastAPI background task keeps the process single, avoids Redis/broker dependency, and is trivially deployable.

```python
# web/routes/jobs.py
from fastapi import BackgroundTasks

@router.post("/jobs")
def create_job(params: JobParams, background_tasks: BackgroundTasks, db=Depends(get_db)):
    job_id = db.create_job(params)
    background_tasks.add_task(run_pipeline, job_id, params.since, params.until, db)
    return {"job_id": job_id, "status": "pending"}
```

### Pattern 3: Config Snapshot on Job Creation

**What:** When creating a job, snapshot the active config (repos, categories, LLM settings — but NOT secrets) into the job's SQLite row as JSON.

**When:** Always, on every job creation.

**Why:** Config changes over time. The admin might add/remove repos tomorrow. Historical job records should reflect the config that was used when that job ran, so previews are reproducible. Secrets are omitted from the snapshot — re-read from .env at runtime.

### Pattern 4: Separate Preview from Send

**What:** Pipeline execution ends at rendering. Distribution (Slack, email) is a distinct POST action.

**When:** Always. This is the core UX flow.

**Why:** This matches the CLI's `--dry-run` pattern and the PROJECT.md requirement: "User can preview the generated changelog before sending." Never auto-send after generation.

### Pattern 5: Frontend Strategy — htmx over React

**What:** Use htmx for the frontend: server-rendered HTML from FastAPI's Jinja2 templates, with htmx attributes for polling and form submission.

**When:** For this internal tool with simple interaction patterns (form submit, polling, table display, preview render).

**Why:** The project already uses Jinja2 for changelog templates. Using Jinja2 for the web UI templates too means zero additional frontend toolchain (no npm, no build step, no bundler). htmx handles the job polling loop (`hx-trigger="every 2s"`) and form submissions without a single line of JavaScript. React would be engineering overkill for a form → progress bar → preview → send button workflow.

If the stakeholder portal (v2 vision in PROJECT.md) materializes, the API layer is already in place — swapping to React or a separate SPA at that point is straightforward.

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: Subprocess / Shell-out

**What:** Calling `subprocess.run(["python", "changelog.py", "--since", "..."])` from the web layer.

**Why bad:** Creates a separate process that can't share state, returns only stdout/stderr (no structured data), requires parsing text output, breaks on any output format change, and loses Python's exception context. The pipeline is already importable — there is no reason to go through the shell.

**Instead:** Import and call `src/` functions directly.

### Anti-Pattern 2: Storing Secrets in SQLite

**What:** Saving GitHub tokens, Slack tokens, OpenAI API keys in the jobs database or returning them in API responses.

**Why bad:** SQLite is a plain file. Any process with filesystem access can read it. Secrets belong only in `.env`.

**Instead:** Store only non-secret config in job snapshots. Re-read secrets from `.env` at pipeline execution time.

### Anti-Pattern 3: Blocking the FastAPI Request Thread

**What:** Running the full pipeline synchronously inside a route handler (no background task).

**Why bad:** A changelog generation takes 5-30 seconds (network I/O + OpenAI call). Blocking the request thread means the browser hangs, timeouts occur, and the server is unresponsive during generation.

**Instead:** Use BackgroundTasks to run the pipeline. Return `202 Accepted` with a job ID immediately. Have the browser poll for completion.

### Anti-Pattern 4: Overwriting config.yaml Without Validation

**What:** Accepting raw YAML from a web form and writing it directly to config.yaml.

**Why bad:** A malformed YAML write corrupts the config for both the web app AND the CLI. This is a critical failure path.

**Instead:** Parse the form fields into a typed config dict, validate required fields, then serialize back to YAML using `yaml.dump()`. Never accept raw YAML text from users.

### Anti-Pattern 5: Adding a Message Queue (Celery/RQ/Redis)

**What:** Introducing Celery, RQ, or Redis for task queuing.

**Why bad:** This is an internal tool with infrequent, sequential changelog runs. A message broker adds deployment complexity (two additional services), operational overhead, and a harder local development story — all for zero benefit over FastAPI's built-in background tasks.

**Instead:** Use `fastapi.BackgroundTasks`. If the tool ever needs true async scale (it won't), migrate then with evidence.

---

## Suggested Build Order

This order is driven by dependencies: you cannot render a preview without running the pipeline; you cannot run the pipeline without a job model; you cannot build config UI without reading config structure.

```
1. Foundation layer
   → FastAPI app skeleton + SQLite schema (jobs table)
   → In-process pipeline runner (wraps existing src/ functions)
   → POST /jobs + GET /jobs/{id} (trigger + poll)
   Dependency: none. This proves the core loop works.

2. Preview layer
   → GET /jobs/{id}/preview (renders stored HTML/Slack/Markdown outputs)
   → Frontend: form + progress polling + preview display
   Dependency: foundation layer complete.

3. Send layer
   → POST /jobs/{id}/send (calls distributors)
   → Marks job as sent in SQLite
   Dependency: preview layer complete (send is an action on a completed job).

4. History layer
   → GET /history (lists past jobs)
   → Linking back to previews
   Dependency: jobs table has data (foundation layer).

5. Config admin layer
   → GET/PUT /config (reads/writes config.yaml + .env)
   → Form UI for repos, tokens, categories, distribution
   Dependency: independent of job flow, but depends on FastAPI skeleton.
```

---

## Scalability Considerations

| Concern | At current scale (1-5 ops, internal) | At 50 users | At 500 users |
|---------|--------------------------------------|-------------|--------------|
| Job execution | BackgroundTasks, single process | BackgroundTasks still fine | Consider RQ/Celery + Redis |
| Storage | SQLite flat file | SQLite flat file | Postgres |
| Config management | config.yaml + .env file | config.yaml + .env file | DB-backed config table |
| Auth | None (v1 scope) | HTTP Basic Auth or simple token | Proper auth service |
| Concurrent generations | 1-2 simultaneous is fine | Queue jobs if same period | Worker pool |

For v1, none of the "at scale" concerns apply. Design for current scale, don't pre-optimize.

---

## Key Architectural Decisions

| Decision | Rationale |
|----------|-----------|
| FastAPI over Flask | FastAPI has native BackgroundTasks, Pydantic validation, and auto-generated docs. Flask requires add-ons for all of these. Both are equally viable; FastAPI is the current ecosystem default. Confidence: HIGH |
| SQLite over Postgres | Zero infrastructure dependency. Internal tool. File-based. Trivially deployable. Upgrade path exists if needed. Confidence: HIGH |
| Direct import over subprocess | Same language, same process, no parsing overhead, full exception context. No tradeoff. Confidence: HIGH |
| htmx over React | No build tooling. Project already uses Jinja2. Interaction complexity is low. Confidence: MEDIUM (would revisit if stakeholder portal becomes v2 priority) |
| Monolith over separate frontend/backend | Eliminates CORS, reduces deployment surface, matches team size and tool complexity. Confidence: HIGH |
| config.yaml remains source of truth | CLI must stay functional. Web UI reads/writes the same file. Confidence: HIGH |

---

## Sources

- Direct codebase analysis: `changelog.py`, `src/config.py`, `src/llm.py`, `src/generator.py`, `src/parser.py`
- FastAPI BackgroundTasks documentation pattern (HIGH confidence — FastAPI docs, well-established pattern)
- SQLite as embedded job store for internal tools (HIGH confidence — standard practice, no external source needed)
- htmx + Jinja2 for server-rendered internal tools (MEDIUM confidence — well-established pattern, training data through Aug 2025)
