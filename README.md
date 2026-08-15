# Career OS

**Personal AI Career Operating System — an AI automation, agent orchestration, and workflow-engineering portfolio project.**

Career OS turns a job search into a controlled, observable workflow rather than a collection of disconnected AI chats and spreadsheets.

## Portfolio value

This project demonstrates practical hands-on work across:

- AI agent orchestration and multi-stage LLM workflows
- Workflow automation with GitHub Actions
- API and OAuth integrations
- Gmail, GitHub, and Notion automation
- Data pipelines, JSON contracts, and deduplication
- Product and systems thinking
- Deterministic validation and quality gates
- Failure handling, recovery, and operational handoffs
- Browser automation architecture with explicit human-control boundaries
- AI-assisted application development

See the [portfolio project profile](docs/PORTFOLIO-PROJECT.md) and [skills evidence matrix](docs/SKILLS-MATRIX.md) for the capability mapping.

## Live workflow

`Job Alert / ATS Discovery / Browser Capture → Deduplicate → JD/Fit → JD-specific Resume → Truth Guard → ATS → Notion Tracking → Browser Execution → Verification → Continue`

## Current architecture

- **Browser control plane:** `src/career_os/api.py` exposes a small FastAPI surface for durable objectives, tasks, approvals, memory, audit events, usage, agents, models, and routing. It serves the existing dashboard when run from the repository and remains usable when all AI providers are unavailable.
- **Durable platform state:** `src/career_os/control_plane.py` stores typed task, agent, model, message, approval, memory, audit, and usage records atomically in `CAREER_OS_CONTROL_PLANE_PATH` (default `.career_os/control_plane.json`). The storage interface is deliberately database-shaped so a managed database adapter can replace the JSON adapter later without changing the contracts.
- **Master Career Profile projection:** `src/career_os/master_profile.py` provides immutable versioned proposals and approvals. Only verified facts are exposed through `facts_for_resume()`; the existing Notion Evidence Vault remains the production source of truth.
- **JD/Fit + Resume + Challenger runtime:** Career OS agent runtime using configured specialist providers where available.
- **Job Capture:** Chrome extension → GitHub issue intake, public employer ATS discovery, and Gmail job-alert intake.
- **Gmail intake:** GitHub Actions polls Gmail every 10 minutes using readonly OAuth refresh-token credentials, extracts role/company/location/link data, deduplicates by Gmail message ID, creates the standard Career OS intake issue, and processes the same pipeline.
- **Review Queue:** Notion API.
- **Application:** The Career OS Application Mode contract determines `AUTO_APPLY`, `REVIEW_REQUIRED`, or `DO_NOT_APPLY`. An authenticated browser executor follows the verified `application_url`, discovers the live application channel, inspects every page, and supplies verified form/attachment facts; only then can `AUTO_APPLY` unlock.
- **Tracking:** Notion + configured secondary trackers.

Discovery tools remain sources/inputs; Career OS does not bypass their access controls.

## AI agent system

Career OS separates AI generation from deterministic control. The current coordination protocol defines specialist roles for JD analysis, evidence retrieval, fit evaluation, resume generation, Truth Guard validation, ATS auditing, independent challenge, Notion/application writing, and controlled browser execution.

GitHub and Notion provide shared state so agents do not depend on manual copy/paste handoffs. Failures are converted into structured engineering handoff issues containing the run identifier, pipeline stage, exact error, likely root cause, artifact/run URL, and safe next action.

See [AI Agent Coordination](docs/AI-AGENT-COORDINATION.md) for the detailed protocol.

## Browser control-plane development

Install the project and run the browser service locally with:

```bash
pip install -e .
uvicorn career_os.api:app --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000/` to use the dashboard. The dashboard first attempts to load the authoritative Notion snapshot and then connects to `/api/dashboard` when the API is present. If the API or snapshot is unavailable, it remains explicit about what is missing rather than inferring job or application state. The objective form queues durable task records through `POST /api/objectives`; consequential actions enter the approval center through the approval endpoints and are not executed automatically by this foundation layer.

The default JSON persistence is intended as a restart-safe development adapter. For cloud deployment, set `CAREER_OS_CONTROL_PLANE_PATH` to a persistent mounted location or replace `ControlPlaneStore` with a managed database adapter. No credentials belong in the repository.

## Automation and integrations

### GitHub Actions

The repository uses workflows for job discovery/intake, Gmail ingestion, application execution queues, question intake, readiness recalculation, failure handoff, recovery, self-healing, dashboard synchronization, specialist-source intake, and validation.

### Gmail

Read-only Gmail OAuth is used to ingest job-alert messages into the same Career OS pipeline. The worker does not send, delete, or modify Gmail messages.

### Notion

Notion is used as the career/application data layer for the Career Evidence Vault, Jobs, Resume Library, review records, and Applications.

### Browser execution

Browser execution is treated as a separate authenticated execution boundary. Career OS verifies the application path and exact resume artifact before an eligible automated submission can proceed.

## Delegated AUTO_APPLY authority

The user has explicitly authorized **standing delegated submission authority**. A separate per-job confirmation is **not required** when Career OS deterministically returns `AUTO_APPLY`.

`AUTO_APPLY` is granted only when all existing safety conditions pass: the job is active and non-duplicate, fit qualifies, Truth Guard passes, a verified JD-specific resume exists, the verified `application_url` reaches a legitimate destination, the live channel is discovered rather than assumed, every page in the application flow has been inspected, the exact current resume is attached, every required answer is approved and truthful, and there is no CAPTCHA, OTP/MFA, identity/legal/sensitive gate, unresolved sponsorship/work-authorization issue, compensation decision, assessment, unknown mandatory field, suspicious redirect, unsupported claim request, or other human-controlled step.

When any such condition fails, the application is `REVIEW_REQUIRED` and the exact blocker must be recorded. These gates must never be weakened to increase application volume.

After an AUTO_APPLY submission, the browser executor must verify authoritative employer/ATS/LinkedIn confirmation and the exact submitted tailored-resume hash before the application is marked submitted/applied in Notion. Reaching an employer site, an ATS, a form, or an upload state is never proof of submission.

## Resume safety

Only the exact current JD-specific PDF/DOCX generated by Career OS may be attached. If normal upload fails, the browser operator may use the controlled file-input/file-chooser fallback and must verify the exact filename. The master resume is never a fallback.

The orchestrator also accepts a verified browser-context JSON file through `--browser-context-json`. This is the handoff boundary between the authenticated browser executor and the deterministic Career OS safety engine.

## Gmail setup

Create a Google Cloud OAuth desktop/web client with the Gmail API enabled and authorize the readonly Gmail scope. Store the resulting OAuth client ID, client secret, and long-lived refresh token as GitHub Actions secrets:

- `GMAIL_CLIENT_ID`
- `GMAIL_CLIENT_SECRET`
- `GMAIL_REFRESH_TOKEN`

Optional repository variable: `GMAIL_QUERY` controls the Gmail search query. The default scans recent job/career/hiring/support alerts. The worker is intentionally read-only and never sends, deletes, or modifies Gmail messages.

## TCS controlled answer

For the TCS question `How many years of Engineering experience do you currently have?`, the approved answer is exactly `0 years`. Technical-support experience must not be reinterpreted as engineering experience.

## Truthfulness rules

- No fabricated metrics.
- No invented certifications.
- No invented employers, dates, titles, degree, tools, responsibilities or production experience.
- Learning/lab exposure must not be silently converted into professional experience.
- If evidence is missing, flag it as a gap.
- A high ATS score never overrides factual accuracy.
- CAPTCHA, OTP/MFA, identity verification, legal/sensitive questions, compensation decisions, assessments, unknown mandatory questions, and other human-controlled gates always stop automation.

## Verified browser manifest and specialist-source intake

Career OS can generate a dispatcher-compatible browser-execution manifest only after all `AUTO_APPLY` gates are revalidated, the exact resume SHA-256 is recorded, and durable Notion Application and Resume Library records exist. The dispatcher revalidates each manifest record before creating a browser task; any invalid record is blocked without inferring submission.

Jobright and Simplify are handled as **authorized browser-capture or JSON-export sources**, not undocumented APIs. The reviewed official materials describe user-profile plus browser-extension autofill workflows. Career OS preserves source attribution, deduplicates records centrally, and returns items through the normal verification and review pipeline. See [the operating runbook](docs/verified-browser-manifest-and-source-intake.md) for commands, manifest fields, and supported access boundaries.

## Portfolio disclaimer

Career OS is a personal project. It demonstrates independent hands-on capability in AI automation, product/system design, integrations, workflow engineering, and application development. It should not be used to claim professional production experience at a previous employer unless that experience is independently supported by employment evidence.
