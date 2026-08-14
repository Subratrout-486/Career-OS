# Career OS — Portfolio Project

## Portfolio positioning

**Career OS is an AI-powered career automation platform and engineering portfolio project.**

It demonstrates how a real-world workflow can be decomposed into AI-assisted analysis, deterministic validation, automation, integrations, human-control boundaries, and observable execution.

## What the project demonstrates

### AI and agent systems

- Multi-stage AI workflow orchestration
- Specialist agent roles for JD analysis, evidence retrieval, fit analysis, resume generation, ATS auditing, and challenge/review
- Provider-aware generation and independent challenger architecture
- Structured agent handoffs through GitHub and Notion
- Failure handoff and recovery workflows

### Automation and workflow engineering

- Automated job intake from multiple supported sources
- Deduplication and pipeline routing
- Scheduled Gmail job-alert ingestion using read-only OAuth credentials
- GitHub Actions workflow orchestration
- Automated readiness recalculation and recovery
- Verified browser-execution handoff
- Application state tracking and post-submission verification

### Product and systems thinking

- Designed around a real user problem rather than a single AI prompt
- End-to-end workflow from opportunity discovery to application tracking
- Explicit state transitions and safety gates
- Separation of engineering state from career/application state
- Human-in-the-loop controls for ambiguous or high-risk actions

### Data and integrations

- GitHub as engineering/control-plane state
- Notion as career/application data state
- Gmail intake integration
- Browser-capture and browser-execution boundaries
- JSON-based pipeline artifacts and browser-context handoffs
- External AI-provider integration through a configured runtime

### Reliability, safety, and quality

- Deterministic Truth Guard for unsupported career claims
- ATS auditing without fabricating keywords
- Exact resume artifact verification
- Explicit `AUTO_APPLY`, `REVIEW_REQUIRED`, and `DO_NOT_APPLY` states
- CAPTCHA, OTP/MFA, legal/sensitive, assessment, compensation, and unknown-field gates
- Failure issues with structured root-cause handoff
- GitHub Actions validation and self-healing workflows

## Skills demonstrated

`AI Agents` · `Agent Orchestration` · `Workflow Automation` · `GitHub Actions` · `REST/API Integration` · `OAuth` · `JSON` · `Data Pipelines` · `LLM Integration` · `Prompt Engineering` · `Product Thinking` · `Systems Design` · `Incident/Failure Handling` · `Deterministic Validation` · `Quality Assurance` · `Browser Automation Architecture` · `Notion Integration` · `Gmail Integration` · `Git/GitHub` · `Documentation`

## Important portfolio honesty rule

Career OS is a personal portfolio project. Technologies or workflows demonstrated here must not be presented as professional production experience at a previous employer unless that experience is independently supported by the user's employment evidence.

The project is intended to demonstrate **independent hands-on capability** in AI automation, product/system design, integrations, and application development.

## Suggested resume entry

**Career OS — AI-Powered Career Automation Platform | Personal Project**

Designed and developed an AI-powered career automation platform that orchestrates job discovery, JD analysis, evidence-based fit assessment, JD-specific resume generation, ATS auditing, application readiness, browser-execution handoff, and application tracking. Implemented GitHub Actions automation, Gmail job-alert ingestion, GitHub/Notion shared-state workflows, deterministic truth/safety gates, structured agent handoffs, failure recovery, and submission verification.

## Suggested interview story

> I built Career OS to solve my own job-search workflow problem. Instead of treating AI as a chatbot, I designed it as a system of specialized stages. A job can enter through an automated intake, get analyzed against verified career evidence, produce a tailored resume, pass deterministic truth and ATS checks, and then move into a controlled application workflow. I used GitHub and Notion as shared state and GitHub Actions to automate recurring workflows. The interesting engineering challenge was not just generating content with AI; it was deciding where AI should be used, where deterministic rules should control the system, and where automation must stop for human review.
