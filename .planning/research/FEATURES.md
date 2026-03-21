# Feature Landscape

**Domain:** Web UI for internal changelog generation and distribution tool
**Researched:** 2026-03-21
**Confidence:** HIGH (CLI source read directly; changelog SaaS comparisons from training data on stable products)

---

## Context: What This UI Is Wrapping

The existing CLI has a linear pipeline: fetch commits → parse → LLM summarize → render → distribute.
Key parameters operators must control:

- Date range (`--since`, `--until`, or "since last run")
- Distribution targets (Slack channel, email recipients)
- Tone (`business` | `technical` | `executive` in config)
- LLM on/off, cache bypass
- Which channels to send to (`--only slack`, `--only email`)

The UI must expose these levers without exposing the command line. Admin-level concerns (which repos exist, API tokens) are set once and separated from operator-level concerns (which period, where to send).

---

## Table Stakes

Features that operators expect in any internal tool of this type. Missing = the tool feels broken or incomplete and operators fall back to the CLI or ask devs for help.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **Date range picker** | Core parameter; operators need to define the period before every run | Low | Needs "since last run" shortcut and preset ranges (last 7 days, this week, last month). The CLI already tracks `last_run.json` — UI reads that state. |
| **Generate button with status feedback** | Triggering generation is the primary action; operators need to know it's working (LLM call can take 5–15 seconds) | Medium | Requires async job handling, loading state, and error display. No silent failures. |
| **Inline preview before send** | Operators need to verify content before it reaches stakeholders — non-technical users especially cannot recover from a bad send | Medium | Must show all three rendered formats (Slack, email, markdown) since the same content looks different per channel. Tabs or toggle. |
| **Send button per channel** | Operators need to choose where to send after preview — not a forced all-or-nothing | Low | Maps to `--only slack` / `--only email` / both. Clear confirmation state ("Sent to #product-updates"). |
| **Past changelogs history list** | Operators need to reference what was sent last week; also proves the tool is working over time | Medium | Reads from `./changelogs/` directory where markdown files are saved. Date, period, file link. |
| **Past changelog viewer** | Browsing history is useless if you can't read the content | Low | Renders the saved markdown. No need to re-run generation. |
| **Distribution target display** | Operators must know which Slack channel and which email addresses are configured before sending | Low | Read-only display of current config. Operators should not discover post-send that they hit the wrong channel. |
| **Error state display** | LLM failures, API token failures, repo fetch failures must surface to the operator with a plain-language message | Medium | The CLI already logs warnings to stderr. UI must capture and show these, not swallow them. |
| **"No changes" state** | When a date range has zero commits, the UI must communicate this clearly — not just show an empty list | Low | The CLI returns empty categories; UI needs a dedicated empty state with a helpful message. |
| **Admin: repo list view** | Operators and admins need to know which repos are being tracked | Low | Read-only display of repos from config. Changing repos is admin scope. |
| **Admin: API token status** | Admins must be able to verify tokens are configured (not necessarily see the values) | Low | "GitHub token: configured / missing", not the actual token value. |

---

## Differentiators

Features that are not baseline expectations but meaningfully improve operator experience and trust. These separate a tool operators enjoy from one they merely tolerate.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Tone/format selector per run** | Operators generating for different audiences (engineering standup vs. executive summary vs. stakeholder email) get the right voice without touching config files | Low | Maps to `tone: business | technical | executive` in config. Simple dropdown/segmented control. |
| **Repo inclusion toggle per run** | For a sprint retrospective, an operator may want only the frontend repo; for a release summary, all repos. Letting them toggle per run reduces "generate everything, edit before sending" friction | Medium | The CLI fetches all configured repos; the UI can filter the categorized output before rendering. Requires a pre-send filter step. |
| **LLM toggle per run** | Power operators know when commits are sparse (LLM adds little value) vs. dense (LLM summary is critical). Exposing this saves cost and time | Low | Maps to `--no-llm`. A visible toggle with "AI summary" label makes this discoverable for non-technical users. |
| **Preview format tabs** | Showing Slack, email, and markdown previews side-by-side before send builds operator confidence that each channel looks correct | Medium | The CLI already renders all three formats in every run. Tabs cost little and eliminate surprises about formatting differences. |
| **Generation run log** | A visible log of what the last generation did (repos fetched, commits found, LLM used/skipped, errors) helps operators self-diagnose without asking a developer | Medium | The CLI already prints this to stdout. Capture and display in UI. Collapsible by default. |
| **Commit count badge on preview** | Showing "23 commits across 4 repos" in the preview header gives operators a sanity check before sending — a period with 0 or 1 commit usually means wrong date range | Low | Already available in template context (`total_commits`, `total_repos`). Surface it prominently. |
| **Admin: edit distribution targets** | Changing the Slack channel or adding an email recipient without touching a YAML file is table stakes for admins — but it requires a config write layer | High | Requires the backend to write config.yaml, not just read it. High complexity because config mutation introduces state management risk. |
| **Quick-send preset: "since last run"** | One-click generation for the most common case (weekly send) reduces cognitive load significantly for non-technical operators | Low | The CLI defaults to this; the UI should surface it as the primary path, not bury it behind a date picker. |
| **Copy-to-clipboard for each format** | For operators who want to paste the Slack message manually or forward the markdown to a doc | Low | Standard clipboard API. Useful when distribution is done manually by some operators. |

---

## Anti-Features

Things to deliberately NOT build in v1, with rationale. These are tempting because they appear on competitor feature lists, but they would either increase scope unacceptably, introduce architectural debt, or solve problems this audience does not have yet.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| **Authentication / login system** | Explicitly out of scope per PROJECT.md. Adding auth before the core UI is validated means building infrastructure for an audience and usage pattern that hasn't been proven yet. Auth is a significant surface area (session management, password reset, CSRF, etc.) | Deploy on internal network or VPN. Add auth in v2 when the tool has proven users. |
| **Inline changelog editor** | A rich-text editor for manually tweaking the generated output before send sounds useful, but it creates a "who owns the content?" problem: if operators routinely edit, the LLM prompt quality matters less, and you've built a text editor not an automation tool | Improve LLM prompt quality (tone, domain config) to reduce the need to edit. |
| **Scheduling / recurring generation** | Cron-like recurring sends sound like an obvious feature, but they require background job infrastructure, failure alerting, and a "who notices if it silently fails?" answer. The operator-triggered model keeps humans in the loop | Use the existing CLI with a cron job at the infra layer; document that pattern for power users. |
| **Stakeholder portal (read-only view)** | Explicitly v2 per PROJECT.md. Building a public/stakeholder-facing view before the internal operator UI is stable means shipping a customer-facing surface before the internal UX is understood | Keep generated output going to Slack/email. Revisit when internal operators are satisfied. |
| **Git provider OAuth integration** | Replacing the static token approach with OAuth per-user would be correct long-term but is a significant security and UX surface in v1 | Config tokens set by admin in `.env`; surface token status in admin panel as read-only. |
| **Custom template editor** | Editing Jinja2 templates in a browser code editor is powerful but adds a debugging surface and means the UI must handle template syntax errors gracefully | Expose the `tone` setting as the user-facing customization lever. Template editing stays a developer concern. |
| **Multi-tenant / workspace isolation** | If there's only one team using this tool, multi-tenancy adds zero value while multiplying data model complexity | Serve a single shared config. Revisit if multiple teams adopt the tool. |
| **Notification / email digest when run completes** | The operator is already in the UI triggering the run — they don't need an async notification for a synchronous action | Show success/error state inline in the UI. |

---

## Feature Dependencies

```
Admin: API token status
  └─→ Admin: repo list view (repos only make sense if tokens are configured)

Date range picker
  └─→ Generate button (no generation without a date range)

Generate button
  └─→ Inline preview (preview requires generated content)
  └─→ Generation run log (log populated by the generation job)

Inline preview
  └─→ Send button per channel (send requires approved preview)
  └─→ Preview format tabs (tabs require rendered content for each format)
  └─→ Commit count badge (badge is part of preview context)

Repo inclusion toggle per run
  └─→ Generate button (toggle must be set before generation, not after)

LLM toggle per run
  └─→ Generate button (same — must be set before generation)

Past changelog viewer
  └─→ Past changelogs history list (viewer requires list to navigate from)
```

---

## MVP Recommendation

The smallest set that makes the tool genuinely usable for a non-technical operator end-to-end:

**Phase 1 — Core operator flow:**
1. Quick-send preset: "since last run" (the 80% case, one click to start)
2. Date range picker (for custom periods)
3. Distribution target display (operator knows where content is going before sending)
4. Generate button with status feedback (with loading state and error display)
5. Inline preview before send (Slack view is sufficient for v1; email tab is nice-to-have)
6. Send button per channel

**Phase 2 — Confidence and visibility:**
7. Commit count badge on preview
8. Generation run log (collapsible)
9. Past changelogs history list + viewer
10. "No changes" state

**Phase 3 — Operator customization:**
11. Tone/format selector per run
12. LLM toggle per run
13. Repo inclusion toggle per run
14. Copy-to-clipboard for each format
15. Preview format tabs (Slack + Email + Markdown)

**Phase 4 — Admin:**
16. Admin: API token status
17. Admin: repo list view
18. Admin: edit distribution targets (high complexity — may be own milestone)

**Defer:**
- Everything in Anti-Features above
- Custom template editor
- Scheduling

---

## Competitive Landscape Notes

**Confidence: MEDIUM** (training data on stable products; no live verification performed — WebSearch/WebFetch unavailable)

Tools observed in the changelog/release notes SaaS space (Headway, Beamer, LaunchNotes, Releasenotes.io, Changelogfy, Changefeed) universally include:

- Rich-text editor for manual entry (anti-feature for this tool — generation is automated)
- Public widget / embeddable changelog (stakeholder portal — v2 for this tool)
- Audience segmentation / tagging (irrelevant at internal tool scale)
- Analytics (views, clicks) — relevant only when there's a stakeholder-facing view
- Categories / labels with custom colors — already handled by the CLI's `categories` config

What those tools do NOT typically have:
- Git commit fetching and LLM summarization as the content source (this tool's core differentiator)
- Multi-repo aggregation across providers (GitHub + Bitbucket) in a single changelog

The existing CLI is ahead of the SaaS space in automation. The UI's job is to make that automation accessible, not to replicate the SaaS feature surface.

---

## Sources

- Direct source read: `/changelog.py`, `/config.example.yaml`, `/templates/slack.j2`, `/templates/email.html.j2` — HIGH confidence
- Direct source read: `.planning/PROJECT.md` — HIGH confidence
- Changelog SaaS feature comparisons (Headway, Beamer, LaunchNotes, Releasenotes.io) — MEDIUM confidence (training data, products are stable but feature sets may have evolved)
- Internal tooling UI patterns (Retool, Backstage, standard ops tooling conventions) — MEDIUM confidence (training data)
- Note: WebSearch and WebFetch were unavailable during this research session. Competitive landscape section should be re-verified if recency is critical.
