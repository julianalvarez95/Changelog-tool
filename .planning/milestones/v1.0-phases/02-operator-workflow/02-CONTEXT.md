# Phase 2: Operator Workflow - Context

**Gathered:** 2026-03-22
**Status:** Ready for execution

<domain>
## Phase Boundary

Build the complete operator workflow on top of the Phase 1 API. Operators interact through a web UI to:
1. Configure a changelog run (date range, tone, distribution targets)
2. Trigger generation and watch live progress
3. Send the generated changelog to selected channels and see per-channel results

No changes to CLI. No changes to src/ pipeline. Web layer only.

</domain>

<decisions>
## Implementation Decisions

### Config Exposure
- **D-01:** `GET /config` exposes distribution target metadata (channel name, recipients) and available tones from config.yaml — never exposes `_env` credentials.
- **D-02:** `GET /config` also returns `last_run` date from `last_run.json` so the UI can pre-fill "since last run" as a date value.

### Tone Override
- **D-03:** `POST /jobs` accepts an optional `tone` field. If provided, it overrides `config.changelog.tone` for that job only. Config file is not modified.

### Distribution (Send Endpoint)
- **D-04:** `POST /jobs/{id}/send` accepts `{"targets": ["slack"|"email"]}`. Sends to each selected target and returns per-target `{"success": bool, "error": str|null}`.
- **D-05:** Send endpoint reads rendered text from SQLite (already stored in Phase 1) — no re-rendering.
- **D-06:** Email subject is formatted at send time using the job's `since`/`until` dates and config values.

### Frontend
- **D-07:** Frontend served as a static HTML file from `web/static/`. FastAPI serves it via `StaticFiles` mount.
- **D-08:** Vanilla JS + Tailwind CDN — no build step, no npm, no frameworks. Keeps it deployable without toolchain.
- **D-09:** "Since last run" toggle fetches `GET /config` and uses the returned `last_run` date as the `since` value.

</decisions>

<canonical_refs>
## Canonical References

- `.planning/REQUIREMENTS.md` — GENR-01, GENR-02, GENR-03, GENR-06, GENR-07 are Phase 2's scope
- `.planning/phases/01-backend-foundation/01-02-SUMMARY.md` — what Phase 1 built
- `web/db.py` — `get_job()` returns `slack_text`, `email_html`, `markdown_text` for done/partial jobs
- `web/routes/jobs.py` — existing job routes; `POST /jobs/{id}/send` will be added here
- `web/tasks.py` — `run_pipeline(job_id, since_str, until_str)` — needs tone_override parameter
- `src/distributors/slack.py` — `send(token, channel, text) -> bool`
- `src/distributors/email.py` — `send(gmail_address, app_password, recipients, subject, html_body, from_name) -> bool`
- `config.example.yaml` — distribution config shape: `distribution.slack.channel`, `distribution.email.recipients`

</canonical_refs>
