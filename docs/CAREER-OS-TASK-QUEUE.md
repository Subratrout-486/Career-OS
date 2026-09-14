# Career OS — Persistent Task Queue

This queue is the shared handoff surface for the continuous operating loop. Agents should update or close the corresponding GitHub issue when a task is verified. Do not duplicate the same work in private chats when an existing issue already contains the current evidence.

## P0 — Active blockers

### P0-01 Gmail OAuth recovery

**Owner:** Gmail Intake + Engineering

**Current evidence:** Gmail intake reached Google's OAuth token endpoint and received HTTP 401. Repository secrets exist but credential validity has not been established.

**Next action:** diagnose the exact sanitized OAuth failure; if the old Google account is inaccessible, reconnect the same three expected secret names to a new authorized Google Cloud OAuth client/refresh token. Never expose secret values.

**Success:** Gmail intake reads job-alert messages and produces standard Career OS intake records without touching application execution.

### P0-02 First controlled application

**Owner:** Application Mode + Browser Operations

**Dependency:** an eligible live candidate, valid runtime credentials, and all deterministic gates passing.

**Success:** one real application completes the existing AUTO_APPLY contract and produces authoritative reconciliation evidence. No gate is weakened to achieve this.

### P0-03 Manus runtime validation

**Owner:** Browser Operations + Engineering

**Dependency:** sanctioned runtime containing the Manus credential and execution configuration.

**Success:** live task creation, retrieval/polling, terminal result, and reconciliation are observed. Historical 404 remains unverified until this occurs.

## P1 — Parallel development (must continue even when P0 is blocked)

### P1-01 Observability / Sentry

**Owner:** Observability + Engineering

Add optional Sentry instrumentation with a no-op behavior when `SENTRY_DSN` is absent. Capture sanitized workflow/integration failures and release/commit context. Sentry must not receive secrets, cookies, raw OAuth tokens, or unredacted logs and must not become an application-safety authority.

### P1-02 Remote job discovery

**Owner:** Job Discovery / Manus

Expand normalized discovery to remote Support Analyst, Product Support, Technical Support, Application Support, and adjacent corporate roles, including compensation and location when available. Preserve source attribution and run all candidates through the existing pipeline.

### P1-03 LinkedIn feed/job capture

**Owner:** LinkedIn Intake / Manus

Use authorized browser capture to collect relevant hiring posts and job opportunities from the user's LinkedIn context. Do not scrape or bypass access controls. Captured jobs enter the same deduplication and verification pipeline as all other sources.

### P1-04 Recruiter outreach queue

**Owner:** Outreach / Manus + Engineering

Create a draft-first recruiter outreach workflow: identify publicly available recruiter contact information where legitimately visible, match the recruiter to a verified job, draft a concise referral request, attach only the approved JD-specific resume, and require an explicit outbound-email action boundary. No fabricated recruiter identity or contact information.

### P1-05 Continuous engineering queue

**Owner:** Engineering / coding agent

Consume failure-handoff issues, implement the smallest safe fix, run deterministic tests, and report current-main compatibility. Protected safety modules remain protected from autonomous self-heal.

### P1-06 Dashboard operations view

**Owner:** Product/UI

Expose task queues, agent availability, active failures, current pipeline stage, job-discovery volume, applications, and blockers. Dashboard presentation must not become a second source of truth or directly mutate Notion application state.

## P2 — Product expansion

- Recruiter outreach analytics and response tracking.
- Better remote-job ranking by compensation, fit, and location/work authorization.
- Specialist-source intake improvements for authorized job-alert products.
- Agent reliability/cost/latency reporting.
- Managed database adapter for the control plane.
- Production deployment hardening.

## Operating rule

**Do not stop the whole Career OS because one queue item is blocked.** Agents work independently where dependencies allow it, and the orchestrator records the dependency rather than waiting on the user to coordinate every step.
