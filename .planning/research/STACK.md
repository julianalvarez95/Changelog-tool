# Technology Stack

**Project:** Changelog Tool — Web UI Layer
**Researched:** 2026-03-21
**Confidence:** HIGH (FastAPI/uvicorn via official docs; Tailwind v4 confirmed via official site; htmx via official site; versions noted with confidence levels)

---

## Decision: Coupled Monolith, Not Decoupled Frontend/Backend

**Recommendation: FastAPI + htmx + Jinja2, served as a single Python process.**

Do not decouple into a separate React SPA + Python API. The reasons:

1. The project already uses Jinja2 for changelog templates — zero toolchain addition to use it for HTML pages too.
2. The interaction complexity is low: one form → polling progress → read-only preview → send button. This does not justify a frontend build pipeline, bundler, or SPA framework.
3. No auth in v1 means no JWTs, no CORS setup, no token refresh logic — all complexity that a decoupled frontend introduces.
4. htmx handles the only "dynamic" interaction (job progress polling) with a single HTML attribute: `hx-trigger="every 2s"`. No JavaScript required.
5. A single deployable Python process is dramatically simpler to run internally than a Python API + npm build step + static asset hosting.

**When to revisit:** If the stakeholder portal (v2 vision from PROJECT.md) is built, that surface likely warrants a React SPA because it is customer-facing and may have richer interactions. The FastAPI API layer is already in place at that point — add a React frontend then, with evidence.

---

## Recommended Stack

### Web Framework

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| **FastAPI** | `>=0.115` | HTTP routing, request/response, background tasks, SSE | Native `BackgroundTasks` for async job execution without Celery. Native SSE (`EventSourceResponse`, added 0.135) for streaming generation progress. Pydantic v2 built-in for request/response validation. Auto-generated OpenAPI docs free. Significantly better than Flask for this use case because Flask has no native background tasks, no native SSE, and no native request validation — all require add-ons. |
| **uvicorn[standard]** | `>=0.30` | ASGI server (dev and production) | FastAPI's official recommended server. Comes bundled with `pip install "fastapi[standard]"`. Single command to run: `uvicorn web.app:app --reload` for development. No Gunicorn needed for an internal tool with <10 concurrent users. |

**Confidence:** HIGH — FastAPI docs verified directly. SSE support (EventSourceResponse) confirmed in FastAPI tutorial docs as a built-in feature added in 0.135.

### Database

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| **SQLite** (via Python stdlib `sqlite3`) | stdlib (Python 3.10+) | Job history, rendered outputs, job status | Zero infrastructure. No separate process. Single `.db` file. Internal tool with <10 concurrent users will never hit SQLite's concurrency limits. The project already has no external database — introducing Postgres for an internal changelog tool is unwarranted complexity. |
| **SQLAlchemy** (optional, deferred) | `>=2.0` | ORM if raw SQL becomes unwieldy | Only add this if the schema grows complex enough that raw SQL becomes unmanageable. For v1 with a single `jobs` table, raw `sqlite3` is sufficient. The FastAPI SQL tutorial recommends SQLModel (a SQLAlchemy wrapper) — skip it for v1, add it if v2 needs it. |

**Confidence:** HIGH — SQLite as embedded job store for internal tools is a well-established standard pattern. No external verification required.

### Frontend

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| **htmx** | `2.x` (CDN, no npm) | Dynamic UI without a JavaScript build step | Handles job progress polling (`hx-get`, `hx-trigger="every 2s"`), form submissions (`hx-post`), and partial page updates — the complete interaction surface of this tool. No npm, no bundler, no build step. Include via CDN: `<script src="https://unpkg.com/htmx.org@2.0.4"></script>`. |
| **Jinja2** | `>=3.1.2` (already in requirements.txt) | Server-side HTML templating | Already a project dependency. Use the same templating engine for web UI pages as for changelog output templates. Zero additional dependency. Familiar to anyone maintaining the existing codebase. |
| **Tailwind CSS** | `v4.x` (CDN) | Utility-first styling | Current version is v4.2. Include via CDN Play CDN for dev; compile via CLI for production. Ideal for internal tools because: no custom CSS files to maintain, dark mode built-in, bundle is <10kB after tree-shaking. Significantly faster to style an internal ops tool with utility classes than writing semantic CSS. |

**Confidence:** htmx — HIGH (official site verified). Jinja2 — HIGH (already in project). Tailwind v4 — HIGH (official site confirmed v4.2 current).

### Infrastructure / Supporting

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| **python-dotenv** | `>=1.0.0` (already in requirements.txt) | Load `.env` for web process | Already a project dependency. FastAPI app reads the same `.env` as the CLI. No change. |
| **PyYAML** | `>=6.0.1` (already in requirements.txt) | Read/write `config.yaml` for admin config | Already a project dependency. Admin config endpoint reads config via `yaml.safe_load()` and writes via `yaml.dump()`. Same library the CLI uses. |

---

## What NOT to Use (and Why)

### Do Not Use Flask

Flask is a viable framework but the wrong choice here for three specific reasons:

1. **No native BackgroundTasks.** Flask requires Celery + Redis or a separate threading hack to run the changelog pipeline (5-30 second operation) without blocking the HTTP response. FastAPI BackgroundTasks solves this in 3 lines of code with no additional infrastructure.
2. **No native SSE.** Streaming progress updates from the pipeline to the browser requires Server-Sent Events. Flask does not support SSE natively — it requires a library (`flask-sse`) and Redis. FastAPI has `EventSourceResponse` built-in.
3. **No native request validation.** Flask requires WTForms or marshmallow for form validation. FastAPI uses Pydantic v2 built-in.

Flask's only argument here would be familiarity — but the project currently has no web layer, so familiarity is not a factor.

**Confidence:** HIGH.

### Do Not Use React / Vue / Next.js

A JavaScript SPA framework is overkill for this interaction pattern. The cost:

- Adds `npm` / `node_modules` to a Python project
- Requires a build step before the app can run
- Requires CORS configuration between frontend dev server and FastAPI
- Requires a state manager (Zustand, Redux) for what amounts to: form fields, one loading boolean, and one preview string
- Increases time-to-first-working-UI by several days

The benefit would be a richer interactive experience — appropriate for a customer-facing product, not an internal ops tool used by <10 people. htmx gives 90% of the UX without any of the build complexity.

**Revisit if:** The v2 stakeholder portal is prioritized. That surface is customer-facing and would likely warrant React.

**Confidence:** HIGH.

### Do Not Use Celery / RQ / Redis

The changelog pipeline takes 5-30 seconds and runs at most a handful of times per day by internal operators. FastAPI's built-in BackgroundTasks runs the pipeline in a thread without any broker infrastructure. Adding Celery + Redis for this use case:

- Adds two additional processes (worker + broker) to run locally and in production
- Requires environment configuration for the broker URL
- Adds failure modes (broker unavailable, worker crashed) that don't exist with in-process execution
- Provides zero benefit at this scale

**Confidence:** HIGH.

### Do Not Use Django

Django's ORM, admin panel, migrations, and auth framework are all appealing in isolation, but:

- Django is opinionated toward databases as the primary data source. This project's primary data source is `config.yaml` + `.env` + the external APIs (GitHub, Bitbucket, OpenAI). Django's patterns don't fit.
- Django's admin panel cannot wrap the existing `src/` pipeline without significant adapter work.
- FastAPI integrates with the existing codebase as a thin layer. Django would require restructuring the project around Django conventions.

**Confidence:** HIGH.

### Do Not Use SQLModel (for v1)

SQLModel is built by the FastAPI author as the "perfect ORM for FastAPI." It is a good library. But for v1 with a single `jobs` table and straightforward CRUD, raw `sqlite3` is simpler: fewer dependencies, less abstraction, immediately readable SQL. Add SQLModel if the schema grows.

**Confidence:** MEDIUM (architectural judgment, not a hard technical constraint).

---

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| Web framework | FastAPI | Flask | No native BackgroundTasks, no SSE, no Pydantic validation. Requires more add-ons. |
| Web framework | FastAPI | Django | Too opinionated; Django patterns don't fit a CLI-wrapper tool. |
| Frontend | htmx | React/Vue/Svelte | Overkill build toolchain for simple form → progress → preview flow. |
| Frontend | htmx | Alpine.js | Both are lightweight JS frameworks; htmx is more suited to server-rendered HTML partial updates (polling pattern). Alpine is better for client-side state. For this app, htmx wins. |
| Database | SQLite (stdlib) | PostgreSQL | No infrastructure needed for internal tool at this scale. Upgrade later if needed. |
| Database | raw sqlite3 | SQLAlchemy/SQLModel | Adds abstraction layer not needed for a single-table schema in v1. |
| Task execution | FastAPI BackgroundTasks | Celery + Redis | Catastrophically over-engineered for an internal tool running <10 jobs/day. |
| CSS | Tailwind CSS | Bootstrap | Tailwind v4's utility-first approach produces smaller bundles and more maintainable internal tool UIs. Bootstrap produces larger CSS and leans toward component-level overrides. |
| ASGI server | uvicorn | Gunicorn | Gunicorn is WSGI. FastAPI is ASGI. Use uvicorn; Gunicorn is unnecessary. |

---

## Installation

Additions to the existing `requirements.txt`:

```bash
# Web layer additions
fastapi[standard]>=0.115.0
# uvicorn[standard] is included in fastapi[standard]

# SQLite is Python stdlib — no pip install needed
# Jinja2, PyYAML, python-dotenv already in requirements.txt
```

Frontend assets via CDN (no npm install required):

```html
<!-- htmx 2.x — include in base template -->
<script src="https://unpkg.com/htmx.org@2.0.4"></script>

<!-- Tailwind CSS v4 Play CDN — development only -->
<script src="https://cdn.tailwindcss.com"></script>
```

For production Tailwind (removes unused classes, bundles to <10kB):

```bash
# One-time setup — only needed for production build
npm install -D tailwindcss@4
npx tailwindcss -i ./web/static/input.css -o ./web/static/output.css --minify
```

Note: If the team wants zero npm even in production, the CDN version is acceptable for an internal tool — bundle size is not a production concern for an internal-only app.

Full new requirements section:

```
# Existing
PyGithub>=2.1.1
requests>=2.31.0
slack_sdk>=3.26.0
jinja2>=3.1.2
pyyaml>=6.0.1
python-dotenv>=1.0.0
openai>=1.0.0

# Web UI additions
fastapi[standard]>=0.115.0
```

---

## Project Structure (Web Layer Addition)

```
changelog-tool/
├── changelog.py          # CLI entry point — UNCHANGED
├── src/                  # Existing pipeline — UNCHANGED
│   ├── config.py
│   ├── fetchers/
│   ├── parser.py
│   ├── llm.py
│   ├── postprocessor.py
│   ├── generator.py
│   └── distributors/
├── templates/            # Existing Jinja2 output templates — UNCHANGED
├── web/                  # NEW: web layer
│   ├── app.py            # FastAPI app instantiation, router registration
│   ├── routes/
│   │   ├── jobs.py       # POST /jobs, GET /jobs/{id}, GET /jobs/{id}/preview
│   │   ├── send.py       # POST /jobs/{id}/send
│   │   ├── history.py    # GET /history
│   │   └── config.py     # GET /config, PUT /config
│   ├── tasks.py          # Pipeline runner (imports src/, writes to SQLite)
│   ├── db.py             # SQLite connection + job table CRUD (raw sqlite3)
│   ├── templates/        # Jinja2 HTML templates for web UI pages
│   │   ├── base.html
│   │   ├── index.html
│   │   ├── preview.html
│   │   ├── history.html
│   │   └── config.html
│   └── static/
│       └── output.css    # Compiled Tailwind (production only)
├── config.yaml
├── .env
└── requirements.txt
```

---

## Sources

| Claim | Source | Confidence |
|-------|--------|------------|
| FastAPI BackgroundTasks pattern | https://fastapi.tiangolo.com/tutorial/background-tasks/ | HIGH |
| FastAPI SSE (EventSourceResponse) built-in | https://fastapi.tiangolo.com/tutorial/server-sent-events/ | HIGH |
| FastAPI WebSocket support | https://fastapi.tiangolo.com/advanced/websockets/ | HIGH |
| FastAPI serving static files (SPA-capable) | https://fastapi.tiangolo.com/advanced/custom-response/#staticfiles | HIGH |
| FastAPI recommended ASGI server: uvicorn | https://fastapi.tiangolo.com/deployment/manually/ | HIGH |
| FastAPI + SQLite pattern (SQLModel/raw sqlite3) | https://fastapi.tiangolo.com/tutorial/sql-databases/ | HIGH |
| Tailwind CSS current version v4.2 | https://tailwindcss.com/ | HIGH |
| Flask requires Celery for background tasks | https://flask.palletsprojects.com/en/stable/ | HIGH |
| htmx suitability for server-rendered Python tools | Training data (htmx.org not accessible during session) | MEDIUM |
| Versions of htmx, FastAPI exact patch numbers | Training data (PyPI not accessible during session) | MEDIUM — use `>=` pins in requirements.txt |
