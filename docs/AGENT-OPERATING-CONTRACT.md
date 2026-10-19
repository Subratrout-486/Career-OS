# Career OS — Agent Operating Contract

## Purpose

Career OS is operated as a set of specialist departments sharing one deterministic control plane. The user owns the outcome; the system owns discovery, diagnosis, routing, implementation, testing, and reporting.

Agents must not require manual copy/paste handoffs when a shared GitHub issue, artifact, workflow result, or Notion record already contains the required context.

## Department map

| Department | Primary responsibility | Typical agent | Authority |
|---|---|---|---|
| Orchestrator | Maintain the task queue, dependencies, priorities, and handoffs | Career OS control plane | Coordination only |
| Job Discovery | Find and normalize Support Analyst, Product Support, Technical Support, application-support, and adjacent roles; include remote opportunities | Manus / browser research | Discovery only |
| Gmail Intake | Read job-alert mail and convert valid messages into normal intake records | Gmail worker + engineering agent | Read-only Gmail |
| LinkedIn Intake | Capture relevant feed/job/recruiter opportunities through authorized browser access | Manus | Discovery/capture only |
| Career Evidence | Retrieve authoritative career evidence and preserve provenance | Evidence agent | Read-only evidence retrieval |
| JD Analysis | Extract requirements, risks, and mandatory questions | JD analyzer | Analysis only |
| Resume | Produce JD-specific truthful resume artifacts | Resume agent | Cannot bypass Truth Guard |
| Truth Guardian | Deterministically reject unsupported claims | Deterministic code | Gate authority |
| ATS / Design QA | Measure coverage and presentation quality | ATS/QA agents | Cannot override Truth Guard |
| Independent Review | Challenge fit and application readiness independently | Gemini / independent provider | Review authority only |
| Engineering | Diagnose code/workflow failures, implement small reversible fixes, run tests | Coding agent | Code changes within protected boundaries |
| Observability | Detect, classify, and explain runtime failures | Sentry/Seer when configured | No safety-gate bypass |
| Browser Operations | Perform authenticated browser preflight/execution under Application Mode | Manus | Execution only after deterministic gates |
| Application Tracking | Reconcile verified outcomes into Notion | Deterministic reconciler | Ledger authority |
| Product/UI | Maintain dashboard and operator experience | UI coding agent | Presentation only |

## Priority policy

1. P0 — Restore broken intake/execution paths and preserve application safety.
2. P1 — Increase reliable job discovery and application throughput without weakening gates.
3. P1 — Improve observability and automatic diagnosis.
4. P2 — Improve recruiter outreach, remote-job discovery, dashboard UX, and integrations.
5. P3 — Long-term platform improvements and optional provider integrations.

A blocked P0 does not automatically block independent P1/P2 work unless the dependency is explicit.

## Continuous operating loop

```text
DISCOVER
  -> NORMALIZE
  -> VERIFY
  -> QUALIFY
  -> PREPARE
  -> REVIEW
  -> APPLY WHEN AUTO_APPLY
  -> RECONCILE
  -> OBSERVE
  -> DIAGNOSE
  -> REPAIR
  -> TEST
  -> RETURN TO DISCOVERY
```

The loop is continuous. A single broken integration must not stop unrelated discovery, engineering, dashboard, or observability work.

## Failure routing

Every failure becomes a structured engineering task containing:

- run/workflow identifier
- repository commit
- department
- pipeline stage
- exact sanitized error
- severity and priority
- likely root cause
- relevant workflow/run/artifact reference
- recommended next action
- tests required
- whether a credential/user action is required

The task remains open until an agent reports a verified outcome or explicitly escalates it as `HUMAN_ACTION_REQUIRED`.

## Agent handoff contract

An implementation agent must return:

1. What it inspected.
2. What it changed.
3. Why the change is safe.
4. Tests run and exact result.
5. Remaining blockers.
6. Next dependent task.
7. Whether commit/PR/merge is permitted.

A research agent must return source URLs/evidence and must not silently turn discovery into application state.

A browser agent must never claim submission from page reachability, upload completion, or its own unsupported assertion. Applied remains dependent on the existing deterministic reconciliation contract.

## Safety invariants

No agent may:

- weaken Truth Guard or Application Mode to increase volume;
- turn missing/failed independent review into approval;
- expose secrets or authentication cookies to an external model;
- treat a job-alert source as an application confirmation;
- treat resume upload as submission confirmation;
- mark an application Applied without the authoritative reconciliation requirements;
- modify protected safety files through self-heal;
- use an external browser session as a substitute for a repository/API authorization boundary.

## Provider policy

Providers are replaceable workers, not authorities. If a provider is unavailable, the task should be retried or routed to an eligible fallback. A provider failure must never be converted into a successful safety decision.

Interactive Claude, Cursor, Manus, and Grok sessions are external workers unless an explicit supported integration exists. Career OS must not claim that GitHub Actions can directly invoke an interactive chat session without such an integration.

## Definition of done

A task is `DONE` only when the implementation or diagnosis is verified by deterministic tests or an authoritative runtime observation. "Code exists" or "agent says fixed" is not sufficient.

For production execution work, `DONE` additionally requires current-main compatibility, safety-gate preservation, and explicit runtime evidence where static inspection cannot prove the behavior.
