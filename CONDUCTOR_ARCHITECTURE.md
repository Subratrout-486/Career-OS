# Career OS — Conductor Architecture

Conductor remains the intended orchestration layer. GitHub Actions is the scheduler/durable trigger; Career OS is the source-of-truth, evidence, matching, resume and safety layer; Conductor is the runtime that can assign AI agents to browser/search/apps/sites.

## Intended flow

```text
08:00 / 20:00 IST
      |
      v
GitHub Actions scheduler
      |
      v
Career OS discovery trigger
      |
      v
Conductor / AgentFlow
      |
      +--> Career-site source resolver agent
      +--> Company career-site/job-search agents
      +--> JD extraction/enrichment agent
      +--> Career-fit/evidence agent
      +--> Resume tailoring agent
      +--> ATS/truth/independent-review agents
      +--> Notion/dashboard sync agent
      |
      v
Career OS durable records
      |
      +--> Ready-to-apply queue
      +--> Confirmation questions
      +--> Human approval/browser boundary
      |
      v
Manus/browser execution only when every application gate passes
```

## Why Conductor is required for the full vision

The current repository already has a large company watchlist and a public official-career watcher, but many watchlist entries intentionally have no verified career URL yet. The direct watcher treats those entries as `UNCONFIGURED` rather than guessing a site. This is safe but it cannot by itself behave like a browser-capable agent that discovers and searches every company's career site.

Conductor is the missing orchestration layer for that browser/search work. It can dispatch the specialist agents and tools, collect their results, persist them back into Career OS, and continue the pipeline without manual prompt copying.

## No silent fallback

If Conductor is not connected, Career OS must still run its deterministic public-source watcher, but it must clearly report the reduced coverage. It must not claim that all companies were searched when only configured public feeds/pages were checked.

## Application boundary

Job discovery and resume generation are not the same as application submission. Browser submission remains gated by the existing application-mode, truth, ATS, recruiter-review, form-verification and human-control checks. A discovery run must never create an application task merely because a job looks like a match.
