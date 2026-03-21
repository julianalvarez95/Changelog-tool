# Requirements: Changelog Tool UI

**Defined:** 2026-03-21
**Core Value:** Non-technical operators can generate and send polished changelogs from multiple repos without ever opening a terminal.

## v1 Requirements

### Job Generation

- [ ] **GENR-01**: User can select a date range (from/until) before generating a changelog
- [ ] **GENR-02**: User can select which distribution targets to send to (Slack channels and/or email lists) before generating
- [ ] **GENR-03**: User can configure tone/format (technical detail level) before generating
- [ ] **GENR-04**: User can trigger changelog generation from the UI
- [ ] **GENR-05**: User sees async generation progress while the pipeline runs (5–30s)
- [ ] **GENR-06**: User can send the generated changelog to selected distribution targets
- [ ] **GENR-07**: User sees per-channel send result (success or failure) after sending

### History

- [ ] **HIST-01**: User can browse an archive of all past generated changelogs
- [ ] **HIST-02**: User can open a past changelog entry and view its content

## v2 Requirements

### Job Generation

- **GENR-V2-01**: User can preview generated changelog before sending
- **GENR-V2-02**: User can re-send a previously generated changelog

### Admin

- **ADMN-V2-01**: Admin can add/remove repos and API tokens via UI
- **ADMN-V2-02**: Admin can manage Slack channels and email lists via UI

### Platform

- **PLAT-V2-01**: User authentication (role-based: admin vs operator)
- **PLAT-V2-02**: Stakeholder portal (read-only changelog view for external stakeholders)
- **PLAT-V2-03**: Scheduled / recurring changelog generation

## Out of Scope

| Feature | Reason |
|---------|--------|
| Preview before send | User opted for generate → send direct flow; can be revisited in v2 |
| Admin config management | Config stays in config.yaml + .env for v1; reduces attack surface |
| User authentication | Internal tool assumption; deferred to stakeholder portal milestone |
| Scheduling | Adds background job infrastructure complexity; not needed for v1 |
| Inline changelog editing | Undermines automation value proposition; deliberate exclusion |
| Stakeholder portal | Separate milestone; v2 vision |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| GENR-01 | — | Pending |
| GENR-02 | — | Pending |
| GENR-03 | — | Pending |
| GENR-04 | — | Pending |
| GENR-05 | — | Pending |
| GENR-06 | — | Pending |
| GENR-07 | — | Pending |
| HIST-01 | — | Pending |
| HIST-02 | — | Pending |

**Coverage:**
- v1 requirements: 9 total
- Mapped to phases: 0
- Unmapped: 9 ⚠️

---
*Requirements defined: 2026-03-21*
*Last updated: 2026-03-21 after initial definition*
