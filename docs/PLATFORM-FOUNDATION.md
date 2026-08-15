# Career OS Platform Foundation

**Implementation date:** 2026-08-15

The first implementation slice adds a browser-facing control plane without replacing the existing GitHub Actions pipeline, Notion evidence source, browser execution contract, or deterministic Truth Guard.

## Implemented capabilities

| Capability | Implementation | Safety behavior |
| --- | --- | --- |
| Durable task state | `ControlPlaneStore` and `TaskRecord` | Explicit `QUEUED`, `RUNNING`, `WAITING`, `RETRYING`, `BLOCKED`, `FAILED`, `AWAITING_APPROVAL`, and `COMPLETED` states are persisted atomically |
| Controlled delegation | `PlatformOrchestrator.delegate()` and `AgentMessage` | Messages require a registered target agent; terminal tasks cannot be delegated; agents do not write directly to one another's records |
| Agent registry | `AgentRecord` | Availability, capabilities, health signals, usage, and department are represented as data |
| Model registry/router | `ModelRecord`, `ModelRouter`, and `RouteRequest` | Routing chooses the least expensive available capable model; unavailable or insufficient models produce `WAITING`, not fabricated success |
| Structured memory | `MemoryItem` | Authoritative memory is rejected unless verified; every item records source, timestamp, confidence, status, and provenance |
| Approval center data | `ApprovalRequest` and approval endpoints | Consequential actions can enter `PENDING`; decisions are explicit and audited |
| Audit trail | `AuditEvent` | Objective submission, delegation, task results, approvals, memory, and usage are linked to actors and task IDs |
| Usage tracking | `UsageEvent` | Provider, model, operation, estimated tokens, credits, duration, and success are retained |
| Immutable career facts | `MasterCareerProfile` and `CareerFact` | Proposals default to `UNVERIFIED`; approval creates a new profile version; only verified facts are resume-safe |
| Browser API | `src/career_os/api.py` | FastAPI exposes health, dashboard, objectives, task results, approvals, memory, audit, usage, agents, models, and routing |
| Dashboard bridge | `dashboard/app.js` and `dashboard/index.html` | The static snapshot remains the fallback; the dashboard connects to the API when present and can queue objectives from the browser |
| Proven pipeline adapter | `src/career_os/pipeline_adapter.py` | Existing `CareerOS.process()` runs can be recorded as durable tasks; an `AUTO_APPLY` result becomes a pending approval rather than an automatic browser action |
| Cloud packaging | `Dockerfile` and `.dockerignore` | The API can be deployed to a persistent cloud host with a mounted `/data` volume; credentials and local state remain outside the image |

## API surface

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | Report API health and durable record counts; explicitly marks AI as optional |
| `GET` | `/api/dashboard` | Return tasks, approvals, agents, models, memory, audit, and usage for the command center |
| `POST` | `/api/objectives` | Queue a durable user objective |
| `POST` | `/api/tasks/{task_id}/result` | Record an explicit task result or failure state |
| `POST` | `/api/approvals` | Create a consequential-action approval request |
| `GET` | `/api/approvals` | List approval records, optionally pending only |
| `POST` | `/api/approvals/{approval_id}/decision` | Approve, reject, edit, or retry an approval request |
| `POST` | `/api/memory` | Add a provenance-aware memory item |
| `GET` | `/api/audit` | Inspect task-linked or full audit history |
| `GET` | `/api/usage` | Inspect usage events |
| `GET` | `/api/agents` | Inspect registered agents |
| `GET` | `/api/models` | Inspect registered model records |
| `POST` | `/api/route` | Ask the model router for a cost/capability-aware route |

## Local run contract

```bash
pip install -e .
uvicorn career_os.api:app --host 0.0.0.0 --port 8000
```

The default persistence path is `.career_os/control_plane.json`. For a persistent cloud volume, set `CAREER_OS_CONTROL_PLANE_PATH` to a writable mounted location. The JSON adapter is intentionally replaceable; a managed database adapter can implement the same store methods without changing the browser contracts.

## Validation evidence

The existing repository suite passed before implementation with **200 tests**. After adding the control-plane, browser API, and proven-pipeline adapter coverage, the full suite passed with **211 tests**. JavaScript syntax validation and Python bytecode compilation also passed. A live Uvicorn smoke test verified `GET /api/health`, `POST /api/objectives`, and `GET /api/dashboard` over HTTP. The only reported warning is a test-client deprecation notice from the installed Starlette/httpx combination; it does not affect application behavior.

## Deliberate non-claims

This slice does not claim that a managed production database, hosted cloud URL, external model API, or automatic application submission has been provisioned. Existing Notion, Gmail, GitHub, and authenticated-browser integrations remain governed by their existing connector and workflow boundaries. The new API is a deployment-ready boundary and a safe development adapter, not a fabricated external integration.

The next implementation slice should replace the JSON adapter with a managed database and register connector-backed specialists with real health checks. That work should preserve the independent-challenger rule, the Evidence Vault fail-closed policy, and the existing application-mode gates. A future hosted deployment should also add authentication and authorization around write endpoints before exposing them publicly.
