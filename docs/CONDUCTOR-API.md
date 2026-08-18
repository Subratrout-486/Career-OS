# Career OS Conductor API Boundary

## Purpose

This boundary is the only server-to-server seam between Conductor and the existing Career OS engine. It delegates to `ControlledCareerPipeline`, which delegates to the existing `CareerOS.process` implementation. It does not create a second business engine and it does not submit applications.

## Authentication and safety

Every endpoint under `/api/conductor/v1` requires the server-side `X-Conductor-Token` header. The expected value is read only from `CAREER_OS_CONDUCTOR_TOKEN`; it is never returned in an API response, persisted in a request record, or written to logs. Requests are bounded by Pydantic field limits, and browser/application-submission control keys are rejected.

Pipeline requests require an `idempotency_key`. The boundary stores only the key, trace identifier, and reservation timestamp in the configured idempotency store. It never stores the profile, job payload, provider credentials, or response body in that store. Reusing a key returns HTTP 409, and failed reservations are released for a safe retry. Error responses intentionally omit provider exception text so secrets and request data cannot leak through the API.

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/conductor/v1/health` | Authenticated capability and review-only health check |
| POST | `/api/conductor/v1/pipeline/run` | Run the existing Career OS review pipeline through `ControlledCareerPipeline` |

The health response includes `status`, `boundary`, `engine`, `review_only`, `submission`, and supported capability names. A successful response must report `submission: disabled` and `engine: existing-career-os-process`.

## Pipeline request

```json
{
  "profile": "candidate profile text",
  "job": {
    "company": "Example",
    "title": "Support Engineer",
    "source_url": "https://example.test/jobs/1",
    "apply_url": "https://example.test/apply/1"
  },
  "browser_context": null,
  "existing_application_page_id": null,
  "idempotency_key": "unique-request-key"
}
```

The response is review-only and includes a trace identifier, idempotency key, the existing pipeline result, `application_mode: REVIEW_ONLY`, and `submission_enabled: false`. Even if an internal pipeline result contains an application mode, this adapter does not execute browser actions.

## Authoritative readiness contract

`READY_TO_APPLY` requires all required evidence and quality gates: a usable and verified job description, successful fit analysis, a recommended resume, a passed Truth Guard, required ATS validation, independent review where required, a verified application URL, no critical errors, and complete evidence/provenance. A source URL alone is not an application URL and must leave the job in a non-ready state such as `RESUME_READY` or another explicit blocker state.

## Local and WebDev runtime

For local execution:

```bash
CAREER_OS_CONDUCTOR_TOKEN='server-only-value' \
CAREER_OS_IDEMPOTENCY_PATH='.career_os/conductor_idempotency.json' \
PYTHONPATH=src uvicorn career_os.api:app --host 0.0.0.0 --port 8000
```

For the Manus WebDev custom image, the existing Career OS source is packaged under `career_os_service/` and launched by the server-side runtime manager. Candor calls the API through its server-only Conductor proxy. The public Candor URL is not known until the user publishes the checkpoint; no URL is fabricated before that event. WebDev Autoscale instances may scale to zero and have ephemeral filesystems, so durable production control-plane storage still requires a persistent database or approved mounted volume; this deployment artifact does not claim that persistence has been provisioned.
