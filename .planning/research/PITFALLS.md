# Domain Pitfalls

**Domain:** Web UI wrapper for an internal Python CLI ops tool
**Researched:** 2026-03-21
**Overall confidence:** HIGH — grounded in direct codebase analysis + established patterns for this class of tool

---

## Critical Pitfalls

Mistakes that cause rewrites, data loss, or security incidents.

---

### Pitfall 1: Blocking the Web Server with Synchronous Pipeline Execution

**What goes wrong:** The changelog pipeline (`fetch → parse → LLM → render → distribute`) takes 10–60 seconds. If the web server calls `changelog.py` (or its internals) synchronously inside a request handler, the HTTP worker thread is blocked. Single-worker servers (Flask dev server, Gunicorn with 1 worker) hang for all users while one job runs. Timeout-heavy proxies (nginx, Cloudflare) drop the connection at ~30s, leaving the job running with no feedback path back to the UI.

**Why it happens:** The obvious "wrap CLI in Flask" approach just calls `subprocess.run(["python3", "changelog.py", ...])` or imports the pipeline directly and calls `main()`. Both block the HTTP thread. Developers prototype this way, it works locally with one user, then breaks in production or under any concurrent use.

**Specific risk in this codebase:** `changelog.py:main()` blocks on:
- `ThreadPoolExecutor` fetching multiple repos in parallel (correct internally, but still blocks the caller thread)
- OpenAI API call in `src/llm.py` with no timeout configured — a slow OpenAI response means indefinite block
- Gmail SMTP send in `src/distributors/email.py` — SMTP connect + send is synchronous and can stall

**Consequences:** Broken user experience, job status unknowable after disconnect, duplicate sends if user retries, server unresponsive to other requests.

**Prevention:**
- Run the pipeline in a background job from day one. Options in ascending complexity: `threading.Thread` (simple, no persistence), Celery + Redis (full queue), or `asyncio` with `run_in_executor`. For an internal tool with low concurrency, a simple thread-based job runner with in-memory status store is sufficient for Phase 1.
- Design a `/jobs/{id}/status` polling endpoint (or SSE stream) before building any UI that needs progress feedback.
- Set explicit timeouts on the OpenAI client call (`timeout=60`) and the SMTP connection.

**Warning signs:**
- The UI's "Generate" button makes a `POST` and waits for a `200` with the changelog content
- Any route handler imports and calls `src/` modules directly without a job queue
- Load testing shows server unresponsive after clicking "Generate" while another generation is in flight

**Phase mapping:** Address in Phase 1 (backend foundation) before any UI is built.

---

### Pitfall 2: Secrets Leaking Through the UI Config Screen

**What goes wrong:** The UI includes an admin config screen to manage repos and API tokens. The browser receives the full config dict — including the `config["_env"]` dict containing `GITHUB_TOKEN`, `BITBUCKET_APP_PASSWORD`, `SLACK_BOT_TOKEN`, `OPENAI_API_KEY`, and `GMAIL_APP_PASSWORD` — in a GET response to render the form. These tokens are stored in browser history, logged by dev tools, and visible in any JS network panel.

**Why it happens:** The natural pattern when building config UI is to fetch the current config for display, then POST changes back. Developers render the entire merged config dict (the same one `src/config.py:load_config()` returns) without stripping the `_env` section. The `_env` key is a convenience dict explicitly added for internal pipeline use — it was never intended to be API-exposed.

**Specific risk in this codebase:** `src/config.py:_inject_env_secrets()` constructs `config["_env"]` as a flat dict of all secrets. A naive `return jsonify(load_config())` route exposes all seven credentials in one response.

**Consequences:** API tokens sent to every browser that loads the config page. Visible in browser history, network logs, server access logs if they log request bodies. Permanent exposure if a log aggregator captures them.

**Prevention:**
- Never serialize `config["_env"]` to any API response. Strip it at the API boundary — write a dedicated serializer that returns only structural config (repos, categories, LLM settings) with secrets replaced by boolean presence indicators (`{"github_token_set": true}`).
- For the config form, token inputs should be write-only: display a masked placeholder if set, only POST a new value if the user explicitly changes it.
- Treat `config["_env"]` as internal pipeline plumbing, never as a data transfer object.

**Warning signs:**
- Any route handler calling `jsonify(config)` or `jsonify(load_config())`
- Config form pre-fills token fields with actual token values

**Phase mapping:** Address in Phase 2 (config management UI). Establish the serialization boundary rule before any config API endpoint is written.

---

### Pitfall 3: Duplicate Distribution on Retry or Refresh

**What goes wrong:** A user clicks "Send." The job runs, sends to Slack and email, but returns a 504 (proxy timeout) or the browser tab is closed. The user sees no confirmation, assumes it failed, and clicks "Send" again. The changelog is distributed twice to all recipients.

**Why it happens:** The pipeline lacks idempotency keys. `src/distributors/slack.py:send()` and the email distributor post unconditionally — there is no "already sent for this date range" guard beyond the LLM cache (which is for the OpenAI call, not distribution). `last_run.json` is updated at the end of `main()`, but the UI retry bypasses this check.

**Specific risk in this codebase:** The LLM cache at `changelogs/.intel_cache/{since}_{until}.json` prevents double OpenAI calls but not double distribution. `last_run.json` is a file on disk with no locking — concurrent requests could both read the same state before either updates it.

**Consequences:** Stakeholders receive the same changelog twice (or more). Embarrassing for an internal tool presented as professional. Slack channel becomes noisy. Email recipients unsubscribe.

**Prevention:**
- Assign a job ID at the moment "Generate" is clicked. Track job state: `pending → running → done | failed`. Only allow a send if job state is `done` and `sent_at` is null. Set `sent_at` atomically when distribution succeeds.
- Store distribution records in a simple SQLite table: `(job_id, channel, sent_at, status)`. Check before sending.
- The UI's "Send" button should disable immediately on click and show job state from the polling endpoint.
- The preview-before-send flow (configure → generate → preview → send) is correct — the "Send" step should be guarded by the presence of a completed, unsent job.

**Warning signs:**
- "Generate" and "Send" are a single button or single action
- No job ID is assigned at generation time
- The "Send" endpoint is POST-idempotent in documentation but not in implementation

**Phase mapping:** Address in Phase 1 (job runner design) and Phase 3 (send flow in UI).

---

### Pitfall 4: Config Mutation Race Condition

**What goes wrong:** The web server reads `config.yaml` on startup (or per-request via `load_config()`). The admin saves a new config through the UI. The web server writes the new `config.yaml`. A generation job is running concurrently and is midway through reading the config. The write truncates `config.yaml` before the read completes, resulting in a partial YAML parse error or silent use of stale partial config.

**Why it happens:** `config.yaml` on disk is a file, not a database. Concurrent read/write without file locking is a race condition. Python's `yaml.safe_load()` does not protect against concurrent writes.

**Specific risk in this codebase:** `src/config.py:load_config()` calls `open(config_file)` and `yaml.safe_load(f)` without any lock. If the web server saves a new config by writing to the same path while a thread calls `load_config()`, the read can see a partial write.

**Consequences:** Malformed config causes job crash mid-execution; partial config causes silent wrong-repo fetch or missing credentials.

**Prevention:**
- Write config atomically: write to a temp file, then `os.replace(tmp, config_file)`. `os.replace` is atomic on POSIX.
- Load config once at job start, pass it through the pipeline as an immutable dict — do not reload during job execution.
- For the simplest approach: maintain config in SQLite (or a single JSON file) as the source of truth, and regenerate `config.yaml` only when needed for the CLI fallback path.

**Warning signs:**
- Config save endpoint does `open(config_file, 'w').write(...)` directly
- `load_config()` is called mid-pipeline rather than once at job initialization

**Phase mapping:** Address in Phase 2 (config management).

---

### Pitfall 5: No-Auth Tool Becomes an Accidental Proxy for Internal Networks

**What goes wrong:** The UI allows operators to add arbitrary repo URLs and API base URLs. With no authentication on the web app itself, any user on the internal network (or, if accidentally exposed, the internet) can submit a crafted repo URL pointing to `http://169.254.169.254/` (AWS metadata endpoint), an internal Redis instance, or other internal services. The Python fetcher makes the HTTP request from the server, which has network access to those internal endpoints.

**Why it happens:** SSRF (Server-Side Request Forgery) is enabled by any feature where the server makes outbound requests to user-controlled URLs. The "admin can configure repos and API tokens through the UI" requirement is exactly this. No-auth compounds it: there is no user identity to audit, and any network neighbor can trigger it.

**Specific risk in this codebase:** `src/fetchers/github.py` and `src/fetchers/bitbucket.py` currently use hardcoded API base URLs (`api.github.com`, `api.bitbucket.org`). If the config UI allows free-form API base URL input, SSRF becomes trivially exploitable.

**Consequences:** Internal network enumeration, metadata service credential theft (on cloud VMs), access to other internal services.

**Prevention:**
- Validate all repo URLs and API base URLs against an allowlist of permitted hostnames (`api.github.com`, `api.bitbucket.org`) before use.
- Do not allow free-form URL input for API endpoints in the config UI. Use a `provider: github|bitbucket` selector with hardcoded base URLs in code.
- Document explicitly: "This tool must not be network-accessible outside the team's internal subnet." Add this to the README and deployment notes.
- When auth is added in v2, this risk significantly reduces — but the URL allowlist is a cheap, permanent protection regardless.

**Warning signs:**
- Config UI has a free-text "API base URL" or "custom endpoint" field
- Fetchers use a configurable base URL from config rather than hardcoded constants
- Tool is deployed to a machine with broad internal network access

**Phase mapping:** Address in Phase 2 (config management UI). URL validation is a one-time addition when building repo config forms.

---

## Moderate Pitfalls

---

### Pitfall 6: Changelog History Is File-Based and Fragile

**What goes wrong:** The existing CLI saves markdown files to `./changelogs/changelog-YYYY-MM-DD.md`. The web UI uses this directory as the history store, listing files by name and reading them on demand. The history breaks when: filenames collide (same `until` date, different `since`), files are deleted by accident, the server is restarted on a different machine, or the output directory is remapped.

**Why it happens:** The file-based output was designed for single-operator CLI use. Using it as a queryable database from a web UI is a misuse of the pattern.

**Consequences:** History page shows incomplete records, broken for ranges with same `until` date, no metadata (who sent, which channels, whether it was actually distributed).

**Prevention:**
- Add a lightweight SQLite database (`changelogs.db`) in Phase 1 for history storage. Schema: `(id, since, until, generated_at, sent_at, sent_to, markdown_content, intelligence_json)`. This is a single file, zero-dependency, and works everywhere Python works.
- Keep saving markdown files for the CLI fallback path, but treat SQLite as the authoritative history source for the UI.
- Index by `(since, until)` to prevent duplicates and enable quick lookup.

**Warning signs:**
- History page implementation lists files from `./changelogs/*.md`
- No record of `sent_at` or `sent_to` anywhere in the history data

**Phase mapping:** Address in Phase 1 (data layer) before building the history UI in a later phase.

---

### Pitfall 7: LLM Response Latency Breaks the Preview UX

**What goes wrong:** The user clicks "Generate." The UI shows a spinner. 45 seconds later, either the preview appears or a generic error message shows. There is no intermediate feedback about what the pipeline is doing (fetching commits, calling OpenAI, rendering). Users assume the tool is broken and click again.

**Why it happens:** The pipeline has four distinct stages with different latency profiles. Developers wire up a single job-complete event rather than stage-level progress events. The LLM call is the primary offender: OpenAI `gpt-4o-mini` typically responds in 3–15 seconds but can spike to 45+ seconds under load, and the current code has no timeout.

**Specific risk in this codebase:** The LLM cache (`changelogs/.intel_cache/`) means the second generation for the same date range is fast (cache hit). Users experience wildly different latency: instant on cache hit, 30s+ on cache miss. This inconsistency confuses users more than consistent slowness would.

**Prevention:**
- Add explicit stage status updates to the job runner: `fetching_commits`, `calling_llm`, `rendering`, `complete`. Poll this from the UI and display the current stage.
- Set a timeout on the OpenAI client: `OpenAI(api_key=api_key, timeout=60.0)`. After timeout, fall back to no-LLM mode and indicate in the UI that LLM was skipped.
- Show cache hit status in the UI ("Using cached analysis from previous generation").

**Warning signs:**
- Job status endpoint returns only `running` or `done`, no stage information
- No timeout configured on `OpenAI()` client constructor

**Phase mapping:** Phase 1 (job runner) should include stage tracking. Phase 2 (UI) should display it.

---

### Pitfall 8: Config Persistence Across Generations Is Undefined

**What goes wrong:** The user configures a date range, selects channels, and clicks "Generate." Then they navigate away and come back. The configured date range is gone. They re-configure with slightly wrong dates, regenerate, and send a duplicate for an overlapping period.

**Why it happens:** There is no explicit model for "a generation job has configuration attached to it." The UI treats config as transient form state. When the page reloads, it resets. The `last_run.json` file tracks only the last `until` timestamp, not the full configuration state of the last job.

**Specific risk in this codebase:** The `since_last_run` logic in `changelog.py:resolve_dates()` auto-computes `since` from `last_run.json`. If the web UI sends explicit `since`/`until` to override this, but the user navigates away and loses those values, the auto-computed dates on the next run may produce an overlapping or gap-having range.

**Prevention:**
- Persist each generation job as a record in the history database immediately when "Generate" is clicked, before the pipeline runs. Include `since`, `until`, `channels`, `tone`, and `job_id`.
- On the generation page, show the last generated period prominently ("Last generated: Mar 10 – Mar 17") to help users avoid overlaps.
- The history page should make it immediately obvious if there is a gap or overlap in the sequence of generated changelogs.

**Warning signs:**
- "Generate" button POST body is ephemeral form data not stored server-side
- The history page shows only successfully sent changelogs, not all generated ones

**Phase mapping:** Phase 1 (job + history data model), Phase 3 (history UI).

---

### Pitfall 9: The `.env` File Is Not Editable Through the UI

**What goes wrong:** The UI includes a config screen for repo and API token management. Operators go to save a new GitHub token. The web server writes it to `config.yaml` (structured config). But `GITHUB_TOKEN` is loaded from `.env` by `load_dotenv()`. The config screen overwrites the wrong place. The UI shows the new token as saved, but the pipeline still uses the old token from `.env`.

**Why it happens:** The split config design (`config.yaml` for structure, `.env` for secrets) is correct for CLI use. The web UI must understand this split and handle both files appropriately. Developers often miss that `src/config.py:load_config()` calls `load_dotenv()` which reads `.env`, and that the merged `config["_env"]` dict is derived from environment variables, not from `config.yaml`.

**Specific risk in this codebase:** The `_inject_env_secrets()` function reads from `os.getenv()` after `load_dotenv()`. Changing a value in `config.yaml` does not change what `os.getenv()` returns. A config UI that writes to `config.yaml` for secrets will silently have no effect.

**Prevention:**
- Decide on a single source of truth for secrets in the web context. Options: (a) write secrets to `.env` file via the config UI, (b) store secrets in SQLite and load from there instead of `.env` for the web context, or (c) require secrets to be set only via environment variables and provide a clear "not set — provide via environment" indicator in the UI.
- Document explicitly which values are editable through the UI vs. must be set via environment.
- Do not let the config UI create a false impression that a secret was saved when it was written to the wrong location.

**Warning signs:**
- Config UI save handler writes to `config.yaml` only
- No test to verify that a saved token is actually used in the next pipeline run

**Phase mapping:** Phase 2 (config management). This design decision must be made before building any token input fields.

---

## Minor Pitfalls

---

### Pitfall 10: `last_run.json` Becomes a Corruption Point

**What goes wrong:** `last_run.json` is read and written by both the CLI and the web server. If the web server updates it after a UI-triggered run, subsequent CLI runs auto-compute the wrong `since` date. If the web server is writing `last_run.json` when someone manually runs the CLI, a partial write produces invalid JSON on the next read.

**Prevention:**
- Write `last_run.json` atomically (write to temp, then `os.replace`).
- Consider migrating `last_run` state into the history database where it is transactional.
- Document that the UI and CLI share this file.

**Phase mapping:** Phase 1 (data layer design).

---

### Pitfall 11: Markdown Output Filename Collisions

**What goes wrong:** The current CLI names markdown files `changelog-{until.strftime('%Y-%m-%d')}.md`. Two runs with the same `until` date but different `since` dates produce the same filename. The second run silently overwrites the first.

**Prevention:**
- Name output files by `{since}_{until}.md` or by job ID.
- This is low priority if history moves to SQLite (the file is then just an export artifact), but should be fixed before the UI can trigger multiple generations with the same `until` date.

**Phase mapping:** Phase 1 (output naming).

---

### Pitfall 12: No Feedback When Distribution Partially Fails

**What goes wrong:** The pipeline sends to Slack successfully but email fails (SMTP timeout). `src/distributors/email.py:send()` prints a warning to stderr. In the web context, stderr is invisible to the user. The UI reports "Sent successfully" because the job did not raise.

**Prevention:**
- Capture return values from both distributors. `slack.py:send()` already returns `bool`. Email should do the same.
- Surface partial success in the UI: "Sent to Slack. Email failed: SMTP timeout."
- Store per-channel send status in the history database.

**Phase mapping:** Phase 3 (send flow + result display).

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|----------------|------------|
| Phase 1: Backend foundation / job runner | Blocking HTTP thread (Pitfall 1) | Design job queue + status endpoint before any route handler calls the pipeline |
| Phase 1: Data layer | File-based history fragility (Pitfall 6) | Introduce SQLite history table in Phase 1, not as a later refactor |
| Phase 1: Data layer | `last_run.json` corruption (Pitfall 10) | Atomic writes; consider migrating to DB |
| Phase 2: Config management UI | Secrets leaking in API responses (Pitfall 2) | Write serializer that strips `_env` before Phase 2 any config endpoint is built |
| Phase 2: Config management UI | `.env` vs `config.yaml` secret split (Pitfall 9) | Decide on secrets storage strategy before building token input fields |
| Phase 2: Config management UI | Config race condition (Pitfall 4) | Atomic config writes from day one |
| Phase 2: Config management UI | SSRF via configurable URLs (Pitfall 5) | URL allowlist when building repo config forms |
| Phase 3: Generate → Preview → Send flow | Duplicate distribution on retry (Pitfall 3) | Job ID + idempotency guard before building the Send button |
| Phase 3: Generate → Preview → Send flow | LLM latency breaks UX (Pitfall 7) | Stage-level status tracking in job runner |
| Phase 3: History page | Config state lost between visits (Pitfall 8) | Persist job config at creation time |
| Phase 3: Send result display | Silent partial distribution failure (Pitfall 12) | Capture and surface per-channel send results |

---

## Sources

- Direct analysis of `changelog.py`, `src/config.py`, `src/llm.py`, `src/generator.py`, `src/distributors/slack.py` — HIGH confidence
- `.planning/PROJECT.md` requirements — HIGH confidence
- Established patterns for: SSRF in internal tools, sync-blocking web servers, file-based config races, secrets-in-API-responses — HIGH confidence (well-documented failure modes in this class of tool)
- OpenAI API timeout behavior — HIGH confidence (documented, confirmed in production usage patterns)
