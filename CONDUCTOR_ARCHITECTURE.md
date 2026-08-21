# Career OS — Conductor Architecture

**Conductor/AgentFlow is the AI runtime. Career OS does not require paid LLM API keys.**

GitHub Actions is the deterministic scheduler and durable queue. Career OS is the source of truth, evidence, matching, resume, truth/safety and audit layer. Conductor is the orchestration layer that assigns AI agents and connected tools to browser/search/apps/sites.

## Intended flow

```text
08:00 / 20:00 IST
      |
      v
GitHub Actions scheduler
      |
      v
Deterministic company discovery
      |
      v
Trusted GitHub intake issue
      |
      v
Conductor / AgentFlow
      |
      +--> Career-site source resolver agent
      +--> Company career-site/job-search agents
      +--> JD extraction/enrichment agent
      +--> Career-fit/evidence agent
      +--> Resume tailoring agent
      +--> Truth/ATS/review agents
      +--> Notion/dashboard sync agent
      +--> Browser/app agent when gated
      |
      v
Career OS durable records
      |
      +--> Ready-to-apply queue
      +--> Evidence confirmation questions
      +--> Human-control boundaries
      |
      v
Authenticated browser execution only when Application Mode allows it
```

## No paid-model fallback

GitHub Actions must **not** call xAI/Grok, Gemini, DeepSeek, OpenAI API, GitHub Models, or another paid LLM provider as a fallback. Those dependencies were not part of the intended Career OS design.

If Conductor is disconnected, the deterministic public-source watcher may continue collecting jobs from configured sources. AI processing must remain `READY_FOR_CONDUCTOR`/`CONDUCTOR_NOT_CONNECTED` rather than falling back to an unrelated paid API.

## Why Conductor is required for the full vision

The company watchlist contains many employers whose career URLs are not yet verified/configured. Deterministic public-source discovery can safely process configured sources, but a browser-capable agent is needed to resolve and search the remaining company career sites without manually adding every URL.

Conductor provides that orchestration boundary. It can dispatch specialist agents, collect results, persist them into Career OS, and continue the pipeline without manual prompt copying.

## Application boundary

Job discovery and resume generation are not the same as application submission. Browser submission remains gated by Application Mode, truth, ATS, recruiter-review, form-verification and human-control checks. A discovery run must never create an application task merely because a job looks like a match.
