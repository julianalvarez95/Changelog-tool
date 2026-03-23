# Project Research Summary

**Project:** Changelog Tool — Web UI Layer
**Domain:** Web UI wrapper for an internal Python CLI ops tool
**Researched:** 2026-03-21
**Confidence:** HIGH

## Executive Summary

This project adds a web UI over an existing, fully functional Python CLI changelog pipeline. The CLI already handles the hard parts: fetching commits from GitHub and Bitbucket, parsing with Conventional Commits, summarizing via OpenAI, and distributing to Slack and email. The web layer's job is to make those capabilities accessible to non-technical operators without requiring command-line access. The recommended approach is a coupled monolith — FastAPI serving Jinja2-templated HTML with htmx for dynamic interactions — running as a single Python process. No JavaScript build pipeline, no message broker, no separate worker process. This matches the scale (fewer than 10 internal users), the existing toolchain (Jinja2 already in requirements.txt), and the interaction complexity (form submission, progress polling, read-only preview, send action).

The recommended architecture wraps the existing `src/` pipeline by importing it directly into a FastAPI background task, not by shelling out to `changelog.py`. SQLite (via Python's stdlib `sqlite3`) stores job history, rendered outputs, and send status. This replaces the fragile file-based history pattern the CLI currently uses for the UI's purposes, while leaving the CLI path fully intact. The core operator flow is: configure date range → generate (async, with polling) → preview all formats → send per channel. This maps cleanly to a four-phase build order: foundation (backend + job model), then operator UI (generate/preview/send), then visibility (history, run log), then admin config management.

The key risks are all implementation-level, not architectural: blocking the web server with synchronous pipeline execution (must use BackgroundTasks from day one), leaking API secrets through the config API response (requires a dedicated serializer that strips `config["_env"]` before any API response), and allowing duplicate distribution on retry (requires idempotency guard on the send endpoint). All three are preventable with deliberate, early design decisions and are well-understood failure modes for this class of tool.

---

## Key Findings

### Recommended Stack

The existing project dependency footprint is minimal: PyGithub, requests, slack_sdk, jinja2, pyyaml, python-dotenv, openai. The web layer adds one package: `fastapi[standard]>=0.115.0`, which bundles uvicorn and Pydantic v2. Frontend assets are loaded via CDN (htmx 2.x, Tailwind CSS v4) — no npm, no build step. SQLite is Python stdlib. The resulting deployment artifact is a single Python process running `uvicorn web.app:app`.

Flask was rejected because it lacks native BackgroundTasks and native SSE — both required for non-blocking generation with progress feedback. Celery/Redis was rejected as catastrophically over-engineered for an internal tool running fewer than 10 jobs per day. React/Vue was rejected because the interaction surface (one form, one polling loop, one preview, one send button) does not justify a frontend build pipeline.

**Core technologies:**
- **FastAPI >= 0.115**: HTTP routing, background tasks for async pipeline execution, SSE for progress streaming — native features, no add-ons required
- **uvicorn[standard]**: ASGI server, included in `fastapi[standard]`, single command to run
- **SQLite (stdlib sqlite3)**: Job history, rendered outputs, send records — zero infrastructure, single file
- **htmx 2.x (CDN)**: Job progress polling and form submissions via HTML attributes, no JavaScript required
- **Jinja2 >= 3.1.2**: Already in requirements.txt; used for web UI templates as well as changelog output templates
- **Tailwind CSS v4 (CDN)**: Utility-first styling; Play CDN for dev, CLI compile for production (npm optional)

### Expected Features

The UI exposes operator-level controls (date range, distribution targets, tone, LLM on/off) and separates them from admin-level concerns (which repos, API tokens). Non-technical operators are the primary audience; the UI must not require CLI knowledge.

**Must have (table stakes):**
- Date range picker with "since last run" shortcut — operators need to define the period before every run
- Generate button with loading state and error display — no silent failures; pipeline takes 5–60 seconds
- Inline preview before send (all three formats: Slack, email, markdown) — operators must verify before distribution
- Send button per channel — maps to `--only slack` / `--only email`, with confirmation state
- Distribution target display — operators must know where content is going before clicking Send
- Past changelogs history list and viewer — reference previous sends without re-running generation
- Error state display — LLM failures, API failures, empty result states must surface in plain language
- Admin: API token status (configured/missing indicator, not the actual value)

**Should have (differentiators):**
- Tone/format selector per run — supports different audiences without touching YAML
- LLM toggle per run — power operators can skip LLM for sparse commit periods
- Generation run log (collapsible) — operator self-diagnosis without developer help
- Commit count badge on preview — sanity check before sending ("23 commits across 4 repos")
- Preview format tabs (Slack + Email + Markdown) — eliminates formatting surprises
- Repo inclusion toggle per run — focused changelogs for specific repos or sprints
- Copy-to-clipboard per format — for operators distributing manually
- Quick-send "since last run" as the primary path, not buried behind a date picker

**Defer (v2+):**
- Authentication / login system — deploy on internal network; add auth when proven users exist
- Scheduling / recurring generation — use cron at the infra layer; keep humans in the loop for v1
- Stakeholder portal (public read-only view) — explicitly v2 per PROJECT.md
- Inline changelog editor — if operators routinely edit, fix the LLM prompt instead
- Git provider OAuth integration — static token set by admin in .env is sufficient for v1
- Multi-tenant / workspace isolation — single team, single config for v1

### Architecture Approach

The web layer is a thin wrapper over the existing `src/` pipeline. FastAPI handles HTTP routing and spawns background tasks (not Celery workers) to execute the pipeline by directly importing `src/` functions. SQLite stores job records (status, config snapshot, rendered outputs, sent_at). The existing `changelog.py` CLI entry point and all `src/` modules remain untouched and independently runnable.

**Major components:**
1. **FastAPI app (web/app.py)** — HTTP routing, request validation, job lifecycle management; registers routers for jobs, send, history, config
2. **Background task runner (web/tasks.py)** — imports and calls src/ functions in a thread; writes results to SQLite on completion; emits stage-level status updates
3. **SQLite jobs table (web/db.py)** — persists job ID, status, since/until, config snapshot (without secrets), rendered outputs, sent_at, channels_sent; raw sqlite3, no ORM
4. **src/ pipeline (existing, unchanged)** — fetchers, parser, llm, postprocessor, generator, distributors; called by web/tasks.py via direct import
5. **Config layer (web/routes/config.py)** — reads config.yaml via yaml.safe_load() and .env via file parse; writes atomically; strips secrets from API responses
6. **Frontend (Jinja2 + htmx)** — server-rendered HTML; htmx attributes handle polling (hx-trigger="every 2s") and form submissions; no JavaScript build step

**Key patterns enforced:**
- Never call subprocess/shell out to changelog.py — always import src/ directly
- Never serialize config["_env"] to any API response
- Always run the pipeline in a background task, never synchronously in a route handler
- Config writes use os.replace() (atomic on POSIX) — never direct open(file, 'w').write()
- Distribution is a separate POST action after preview — never auto-send on job completion

### Critical Pitfalls

1. **Blocking the web server with synchronous pipeline execution** — The pipeline takes 10–60 seconds. Running it inside a route handler blocks the HTTP thread, causes browser timeouts, and makes job status unknowable after disconnect. Prevention: design the job queue and `/jobs/{id}/status` polling endpoint before writing any route handler that calls the pipeline. Use FastAPI BackgroundTasks from day one.

2. **Secrets leaking through the config API response** — `src/config.py:load_config()` returns `config["_env"]` containing all seven API credentials. A naive `return jsonify(load_config())` exposes all tokens in one response. Prevention: write a dedicated config serializer that strips `_env` entirely and replaces token values with boolean presence indicators before any config endpoint is built.

3. **Duplicate distribution on retry** — The send endpoint has no idempotency guard. A user who sees a 504 after clicking Send will retry, causing double-distribution to all channels. Prevention: track `sent_at` per job per channel in SQLite; check before sending; disable the Send button immediately on click.

4. **Config mutation race condition** — `src/config.py:load_config()` opens config.yaml without file locking. A concurrent config write can corrupt the read mid-parse. Prevention: write config atomically via `os.replace()` on a temp file; load config once at job start and pass as immutable dict through the pipeline.

5. **SSRF via configurable repo URLs** — The config UI allows adding arbitrary repo URLs. Without URL validation, the server can be directed to fetch internal network endpoints (cloud metadata service, Redis, etc.). Prevention: validate all repo URLs and API base URLs against an allowlist of permitted hostnames (`api.github.com`, `api.bitbucket.org`); never accept free-form API endpoint input.

---

## Implications for Roadmap

Based on research, the build order is driven by strict technical dependencies: the preview page cannot exist without a completed job; the send action cannot exist without a preview; the history page cannot exist without a populated jobs table. Configuration admin is independent but should be deferred until the core flow is proven. Four phases are suggested.

### Phase 1: Backend Foundation

**Rationale:** Everything else depends on this. The job model, background task runner, and SQLite schema must exist before any UI can be built. Getting background task execution correct here prevents the most critical pitfall (blocking the web server). Building SQLite history storage here avoids a later refactor from file-based history.
**Delivers:** A working FastAPI app that can receive a job request, run the changelog pipeline asynchronously, and return job status via a polling endpoint. No UI yet — verified via curl or auto-generated FastAPI docs at `/docs`.
**Addresses:** Core operator flow prerequisites (generate button, status feedback, error handling)
**Implements:** FastAPI app skeleton, SQLite schema (jobs table), web/tasks.py pipeline runner, POST /jobs, GET /jobs/{id}
**Avoids:** Pitfall 1 (blocking web server), Pitfall 3 (duplicate sends — job ID assigned here), Pitfall 6 (file-based history fragility), Pitfall 10 (last_run.json corruption), Pitfall 11 (filename collisions)

### Phase 2: Core Operator UI — Generate, Preview, Send

**Rationale:** This is the primary value delivery phase. With the backend foundation complete, this phase wires the UI to it: the form, progress polling, preview rendering, and send action. The entire operator workflow becomes functional at the end of this phase.
**Delivers:** A non-technical operator can open the web UI, select a date range (or use "since last run"), generate a changelog, preview all three rendered formats, and send to one or both distribution channels — end to end, without touching the CLI.
**Addresses:** All table stakes features: date range picker, quick-send preset, generate button with loading state, inline preview (all format tabs), send per channel, distribution target display, error states, "no changes" state
**Uses:** htmx (hx-trigger="every 2s" for polling, hx-post for form submit), Jinja2 HTML templates, Tailwind CSS, GET /jobs/{id}/preview, POST /jobs/{id}/send
**Avoids:** Pitfall 7 (LLM latency UX — stage-level status tracking), Pitfall 8 (config state lost between visits — job config persisted at creation)

### Phase 3: Visibility and Confidence Features

**Rationale:** Once the core flow works, operators need evidence the tool is working over time and tools to self-diagnose. These features reduce the "did it actually send?" anxiety and developer support requests.
**Delivers:** History list and viewer for past changelogs; generation run log showing pipeline stages and outcomes; commit count badge on preview; per-channel send result display (partial failure surface).
**Addresses:** Should-have differentiators: past changelogs history, generation run log, commit count badge, preview format confidence
**Implements:** GET /history, GET /jobs/{id}/preview (re-render from stored output), partial send failure capture and display
**Avoids:** Pitfall 12 (silent partial distribution failure)

### Phase 4: Admin Config Management

**Rationale:** Admin config is deferred because it is the highest-risk surface area (secrets exposure, config race conditions, SSRF). Building it after the core flow is proven means the team understands the config structure and common operator needs before adding mutation capabilities. The tool is fully functional with static config from .env and config.yaml through phases 1–3.
**Delivers:** Admin UI to view repo list, check API token status (configured/missing), edit distribution targets (Slack channel, email recipients), and change LLM/tone settings — without requiring file system access.
**Addresses:** Admin table stakes (token status, repo list view) and high-complexity differentiator (edit distribution targets)
**Implements:** GET /config, PUT /config, config serializer that strips secrets, atomic config writes, URL allowlist for repo inputs
**Avoids:** Pitfall 2 (secrets in API response), Pitfall 4 (config race condition), Pitfall 5 (SSRF via URL input), Pitfall 9 (.env vs config.yaml secret split)

### Phase Ordering Rationale

- **Dependency chain drives order:** Backend (Phase 1) must exist before UI (Phase 2); preview must exist before send; job records must exist before history (Phase 3). This is not a stylistic choice — it is enforced by the feature dependency graph in FEATURES.md.
- **Risk-front-loading:** The two most dangerous architectural decisions (async job execution, secret serialization) are addressed in Phases 1 and 4 respectively, where they naturally belong. Discovering these late would require rewrites.
- **Admin config deferred deliberately:** The config UI (Phase 4) involves the most pitfalls (secrets leaking, race conditions, SSRF). Deferring it until after the core flow is proven keeps phases 1–3 focused and shippable. Operators can work with static config during this period.
- **Each phase is independently deliverable:** A working, useful tool exists at the end of each phase, not just at the end of all four.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 4 (Admin Config):** The split between config.yaml and .env for secrets requires a decided strategy before building any token input. Three options exist (write to .env via UI, store in SQLite, environment-variable-only); the right choice depends on deployment constraints not yet specified. This design decision needs validation before Phase 4 planning.

Phases with standard patterns (skip research-phase):
- **Phase 1 (Backend Foundation):** FastAPI BackgroundTasks + SQLite job table is a well-documented, standard pattern with official FastAPI tutorial coverage. No novel technical unknowns.
- **Phase 2 (Operator UI):** htmx polling and Jinja2 server-rendered forms are established patterns with high-confidence documentation. The interaction design is simple enough that no additional research is needed.
- **Phase 3 (Visibility Features):** History queries against SQLite and capturing distributor return values are straightforward implementation tasks.

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | FastAPI, uvicorn, SQLite, Jinja2 all verified against official documentation. htmx suitability based on training data (official site not verified live); decision is conservative and well-precedented. Tailwind v4 confirmed as current version. |
| Features | HIGH | Table stakes derived from direct source code read of changelog.py and PROJECT.md. Competitive landscape (Headway, Beamer, LaunchNotes) from training data — MEDIUM for that section specifically, but does not affect must-have feature decisions which are grounded in the codebase directly. |
| Architecture | HIGH | Based on direct analysis of the existing codebase. Component boundaries, data flow, and anti-patterns are grounded in the actual src/ structure. htmx vs. React decision rated MEDIUM by the researcher but is the right call for v1 and reversible for v2. |
| Pitfalls | HIGH | All critical pitfalls are grounded in direct codebase analysis (specific line references to src/config.py, src/llm.py, src/distributors/) and well-documented failure modes for this class of tool. No speculative risks. |

**Overall confidence:** HIGH

### Gaps to Address

- **Secrets storage strategy for config UI (Phase 4):** Three options identified for how the admin UI handles secret tokens (write to .env, store in SQLite, environment-variable-only indicator). The right answer depends on the deployment model (single machine vs. container vs. VM). This decision must be made before Phase 4 planning, not during it.
- **Tailwind v4 CDN in production:** The STACK.md notes that using the Play CDN in production is acceptable for an internal tool (bundle size is not a concern). Confirm with the team whether an npm-free production deployment is preferred. If yes, no action needed. If no, a one-time `npx tailwindcss` build step is the entire change.
- **htmx exact version compatibility:** htmx 2.x was recommended but not verified against a live package registry. Use `>=2.0.4` from the CDN or pin after verifying the current release on unpkg.com at build time.

---

## Sources

### Primary (HIGH confidence)
- Direct source read: `changelog.py`, `src/config.py`, `src/llm.py`, `src/parser.py`, `src/generator.py`, `src/postprocessor.py`, `src/fetchers/github.py`, `src/distributors/slack.py`, `src/distributors/email.py`
- Direct read: `.planning/PROJECT.md`
- https://fastapi.tiangolo.com/tutorial/background-tasks/ — BackgroundTasks pattern
- https://fastapi.tiangolo.com/tutorial/server-sent-events/ — EventSourceResponse (SSE built-in)
- https://fastapi.tiangolo.com/tutorial/sql-databases/ — FastAPI + SQLite pattern
- https://fastapi.tiangolo.com/deployment/manually/ — uvicorn as recommended ASGI server
- https://tailwindcss.com/ — v4.2 confirmed as current version

### Secondary (MEDIUM confidence)
- htmx.org (not verified live during research) — suitability for server-rendered Python tools; htmx 2.x CDN URL
- Changelog SaaS feature comparisons (Headway, Beamer, LaunchNotes, Releasenotes.io) — training data, products are stable but feature sets may have evolved
- Internal tooling UI patterns (Retool, Backstage conventions) — training data

### Tertiary (LOW confidence)
- Exact PyPI version numbers for htmx CDN tag — verify at https://unpkg.com/htmx.org before pinning

---
*Research completed: 2026-03-21*
*Ready for roadmap: yes*
