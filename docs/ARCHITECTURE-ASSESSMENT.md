# Career OS Architecture Assessment and Migration Plan

**Assessment date:** 2026-08-15

**Scope:** Existing repository inspection before implementation changes, based on the current `main` branch and the supplied Career OS specification.

## Executive assessment

Career OS is not an empty prototype. It is a mature Python workflow engine with deterministic safety gates, provider adapters, Notion-backed career evidence, GitHub Actions orchestration, browser-execution handoffs, and a static dashboard. The existing implementation already covers a substantial portion of the requested truthfulness and application-safety behavior. The principal architectural gap is not the absence of agents; it is the absence of a durable, browser-native application and a first-class internal control plane that unifies tasks, departments, model routing, memory, audit events, approvals, and system health.

The safest migration is therefore **extension rather than replacement**. Existing pipeline modules, Notion schemas, GitHub Actions workflows, browser safety contracts, and tests should remain operational while new platform services are introduced behind stable interfaces. The migration should preserve the current fail-closed behavior around evidence and external actions.

## Current implementation inventory

| Area | Current state | Evidence | Assessment |
| --- | --- | --- | --- |
| Frontend | Static responsive dashboard under `dashboard/`, published as a snapshot | `dashboard/index.html`, `dashboard/app.js`, `dashboard/styles.css` | Useful read-only control center, but not an interactive cloud application |
| Backend/runtime | Python package under `src/career_os/` with an async `CareerOS.process()` pipeline | `src/career_os/orchestrator.py` | Strong domain runtime, but no long-lived HTTP/API service |
| Database/state | Notion is the live career/application data layer; GitHub files and Actions artifacts hold engineering and workflow state | `src/career_os/evidence_loader.py`, `docs/AI-AGENT-COORDINATION.md` | Durable but split across external systems; no unified internal task/event store |
| Authentication | OAuth/API secrets are supplied through GitHub Actions and environment variables; browser execution is isolated | `.env.example`, `.github/workflows/` | Appropriate for current automation, insufficient for a multi-user/browser product session |
| Job intake | GitHub issue intake, Gmail polling, public ATS discovery, browser/extension capture | `.github/workflows/career-os-job-intake.yml`, `scripts/` | Broad coverage with durable artifacts and deduplication |
| JD analysis | Structured `JDAnalysis` model and deterministic analyzer | `src/career_os/jd_analyzer.py`, `src/career_os/models.py` | Existing milestone capability |
| Career profile/evidence | Evidence Vault in Notion is authoritative; local snapshot is test-only and production fails closed | `src/career_os/evidence_loader.py`, `src/career_os/evidence.py` | Strong source-of-truth discipline; needs a structured profile projection for the browser UI |
| Resume pipeline | Fit → resume → Truth Guard → ATS → design QA → challenger → review/application persistence | `src/career_os/orchestrator.py` | Already implements most requested quality stages |
| Truth Guardian | Deterministic validation of dates, employers, claims, evidence status, and unsupported content | `src/career_os/truth_guard.py` | Strongest existing safety boundary; must be promoted to a mandatory service contract |
| Model routing | Provider adapters and fallback order exist; challenger independence is explicitly protected | `src/career_os/agents.py`, `src/career_os/specialist_routing.py` | Partial registry/router; usage accounting and persistent task state are missing |
| Multi-agent coordination | Role-specific runtime methods and structured outputs exist; handoff protocol is documented | `docs/AI-AGENT-COORDINATION.md` | Controlled within one pipeline, not yet a general orchestrator/department system |
| Memory | Evidence and application records persist externally; no typed Career/Project/Agent/Task/Decision memory service | `src/career_os/evidence_loader.py`, Notion integrations | Important missing platform capability |
| Audit trail | GitHub issues, Notion records, pipeline JSON, and workflow artifacts provide partial traceability | `.github/workflows/agent-failure-handoff.yml`, `PipelineResult` | Valuable but fragmented; no unified decision/event ledger |
| Human approval | Application Mode and browser gates block consequential actions; the repository documents standing delegated authority for narrowly qualified `AUTO_APPLY` paths | `src/career_os/application_mode.py`, `src/career_os/browser_execution_manifest.py` | Strong safety implementation; browser UI needs explicit approval/reject/edit/retry/source controls |
| Integrations | Notion, Gmail, GitHub, Manus browser lifecycle, and source-intake tools are present | `.env.example`, `src/career_os/`, `.github/workflows/` | Good connector coverage; no centralized integration manager/status API |
| Deployment | GitHub Actions is the main execution/control plane; dashboard is static | `.github/workflows/` | Reliable for event-driven batch work, but not a persistent cloud application backend |

## Baseline validation

The repository was installed using its declared Python project metadata and the expected async test dependency. The current test suite completed successfully with **200 passing tests**. The initial test attempt failed only because the sandbox had not yet installed the project in editable mode and lacked `pytest-asyncio`; after installing the declared runtime and test dependencies, the suite passed without source changes.

This result is important: the migration can start from a green behavioral baseline rather than from a broken implementation. Every subsequent milestone should preserve this suite and add focused tests for new platform behavior.

## Principal gaps against the supplied specification

The supplied specification calls for a persistent browser-based Career Operating System with an orchestrator, departments, controlled messages, a model registry/router, structured memory, usage accounting, audit trails, approvals, integrations, and a central dashboard. The current repository has corresponding concepts, but several are distributed across Python modules, Notion, GitHub, and Actions rather than exposed as first-class platform services.

The most consequential gaps are:

1. **No unified cloud API or application database.** The current system is primarily a batch pipeline plus static snapshot. A browser UI cannot submit objectives, inspect task state, or approve artifacts through a stable internal API.
2. **No durable task graph.** `CareerOS.process()` executes a pipeline in one call. It does not persist a general DAG of tasks, dependencies, retries, timeouts, fallbacks, or escalation state using the explicit statuses required by the specification.
3. **No general department/agent registry.** Specialist behavior exists, but provider capability, health, cost, usage, latency, supported tools, and assignment history are not represented in one registry.
4. **No unified memory or audit service.** Evidence provenance is strong, but Career, Project, Agent, Task, and Decision memory are not modeled together, and the answer to “why did Career OS put this sentence in my resume?” requires navigating multiple artifacts.
5. **No interactive approval center.** Safety gates exist in code, but approval actions are not exposed through a browser-native workflow with durable approval records and explicit `APPROVE`, `REJECT`, `EDIT`, `RETRY`, and source-viewing operations.
6. **AI availability is not fully decoupled from the application surface.** The deterministic modules remain valuable, but the current constructor requires at least one provider for normal runtime creation. A cloud application must be able to load jobs, profile data, resumes, approvals, and audit records when all AI providers are unavailable.
7. **No first-class integration manager.** Integrations are configured by environment variables and workflow-specific secrets rather than presented as individually connectable, permission-scoped services with last-sync and allowed-action status.

## Migration principles

The migration will preserve working functionality and will not replace the existing pipeline wholesale. New services should call existing deterministic modules rather than duplicate their logic. Career facts must remain protected by the existing Evidence Vault/Truth Guard rules. External actions remain approval-gated, credentials remain outside source code, and provider limitations must be surfaced rather than simulated.

The platform should use an **AI-enhanced, deterministic-core** model. Jobs, applications, resume versions, evidence records, approvals, task statuses, audit events, and system health must remain usable without a live model provider. AI tasks should be asynchronous and event-driven, with cached results and explicit failure states.

## Incremental implementation plan

| Milestone | Deliverable | Existing functionality preserved | Validation gate |
| --- | --- | --- | --- |
| 1 | This assessment and migration plan | All source and workflows untouched | Repository inspected; baseline tests green |
| 2 | Typed Master Career Profile projection and durable profile/fact contracts | Existing Evidence Vault remains authoritative | Profile immutability and provenance tests |
| 3 | Agent registry, department catalog, task/message contracts, and orchestrator facade | Existing `AgentRuntime` remains callable | Registry, message isolation, status/retry tests |
| 4 | Mandatory Truth Guardian service boundary and claim provenance ledger | Existing deterministic Truth Guard reused | Fabricated/unsupported/exaggerated claims rejected |
| 5 | JD analysis and job research service adapters | Existing intake and analyzer preserved | Structured JD acceptance tests |
| 6 | Resume engine/ATS service facade and immutable variants | Existing resume files and ATS audit preserved | Variant changes do not mutate source facts |
| 7 | Model router and usage manager | Existing provider fallback and independent challenger rules preserved | Cached routing, provider-disable, and usage tests |
| 8 | Memory and audit event store | Existing Notion/GitHub artifacts preserved | Decision provenance query tests |
| 9 | Browser application dashboard and approval center | Static dashboard remains publishable as fallback | Browser CRUD, approval, and no-AI usability tests |
| 10 | Integration manager and controlled connector boundaries | Existing Gmail, GitHub, Notion, and browser workflows preserved | Permission/status/disconnect tests |
| 11 | Engineering/self-improvement proposal workflow | Production safeguards preserved | Proposal-only default and regression checks |
| 12 | End-to-end acceptance suite and deployment documentation | All prior workflows remain green | Supplied 15-test acceptance suite |

## Recommended first implementation slice

The highest-value low-risk slice is a **platform foundation** consisting of a typed domain layer for tasks, agent registry records, structured messages, approvals, audit events, usage events, and memory items. It can be implemented without changing the existing GitHub Actions production path. A thin HTTP adapter and a browser client can then consume those contracts while the current orchestrator is wrapped as one execution backend.

This slice addresses the core architectural bottleneck—fragmented coordination state—without weakening the existing safety gates. It also creates a path to a cloud-hosted browser UI while allowing the current static dashboard and GitHub Actions workflows to remain operational during migration.

## Known limitations and open decisions

The repository does not currently contain a persistent web backend, a cloud database schema, or a deployment manifest for a browser application. The implementation should therefore avoid claiming that a full cloud deployment already exists. The first code milestone should provide a locally testable service boundary and a deployment-ready contract; selecting a managed cloud database and hosting target should follow from the actual web scaffold and project environment rather than being guessed.

The current README documents standing delegated `AUTO_APPLY` authority for narrowly gated applications, while older setup material describes manual application control. The new platform must treat the executable safety contract in `application_mode.py` and browser verification as authoritative, display the exact blockers, and never broaden automation based only on documentation.

The existing repository is public. No credentials were found in the checked-in source during inspection; secrets must continue to be supplied through environment variables, GitHub Actions secrets, or managed connector configuration.

## Change-control rule

Before each next milestone, run the full test suite, inspect the relevant workflow and module contracts, implement the smallest reversible change, add tests, inspect logs, run regression tests, and update this document with the result. No milestone should be marked complete based solely on a visual dashboard.
