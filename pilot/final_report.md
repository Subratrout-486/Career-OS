# Career OS Manus-Managed Execution Report

## Executive result

Career OS can now use the available Manus-managed OpenAI-compatible endpoint when external Gemini, DeepSeek, xAI, and GitHub Models credentials are absent. The real provider smoke test succeeded with `provider=manus:gpt-5-mini` and returned the expected structured response.

The five-job run was executed in **explicit no-write mode**. It did not create or update Notion records and did not submit applications. No job qualified for browser execution: the run produced **zero `AUTO_APPLY` results**.

## Code changes

| File | Change |
|---|---|
| `src/career_os/agents.py` | Added the Manus-managed OpenAI-compatible provider, configurable through `OPENAI_API_KEY`, `OPENAI_API_BASE`, and `MANUS_MODEL`; `auto` now prefers Manus when available. xAI remains challenger-only and is not replaced by Manus. |
| `src/career_os/models.py` | Added conservative normalization for structured or string-shaped provider outputs. Missing requirement-match fields are marked `UNCONFIRMED`; no missing evidence is promoted. |
| `src/career_os/truth_guard.py` | Accepted known employer display aliases, including `FactSet Systems` versus the canonical profile/evidence employer label, without changing employer attribution or evidence eligibility. |
| `pilot/run_pilot.py` | Added per-job timeout and progress logging. Timeout results are explicitly recorded as `PILOT_TIMEOUT` and default to `REVIEW_REQUIRED`; they are not treated as successful classifications. |
| `tests/test_manus_provider.py` | Added deterministic provider-selection and pinned-provider configuration tests. |

No self-healing files were modified.

## Validation

The complete deterministic suite passed: **72 tests passed**. Python compilation and `git diff --check` also passed.

The real provider smoke test passed using the Manus-managed endpoint and `gpt-5-mini`:

```text
provider=manus:gpt-5-mini
response={"status":"ok"}
```

## Five-job pilot

| Job | Result | Evidence |
|---|---|---|
| Lilly — Senior Application Support Engineer – AI Products & Agents | `DO_NOT_APPLY` | Active; fit score 42; recommendation `REVIEW`; blocked by Truth Guard errors. A truthful resume package was generated in no-write mode. |
| Jobgether partner company — Technical Support Engineer 2 | Not evaluated | `PILOT_TIMEOUT` after 180 seconds; no complete Career OS result. |
| Zimperium — Customer Support Engineer - Endpoint/MTD (Device) & Cybersecurity | Not evaluated | `PILOT_TIMEOUT` after 180 seconds; no complete Career OS result. |
| Jobgether partner company — Support Engineer | Not evaluated | `PILOT_TIMEOUT` after 180 seconds; no complete Career OS result. |
| Lilly — Senior Application Support Engineer – SPE | Not evaluated | `PILOT_TIMEOUT` after 180 seconds; no complete Career OS result. |

Aggregate counts were: **5 discovered, 1 active result, 0 apply recommendations, 0 `AUTO_APPLY`, 4 `REVIEW_REQUIRED` timeout records, 1 `DO_NOT_APPLY`, and 0 submissions**.

## Truth and safety findings

The completed Lilly result was correctly blocked rather than submitted. The Truth Guard identified unsupported employer/tool mappings, including IGT and Concentrix tool claims that were not supported by the approved evidence pack for those employer associations. The run also recorded that the independent xAI challenger was unavailable because `XAI_API_KEY` was not configured. Manus was used as the primary reasoning provider, not as a substitute independent challenger.

Sensitive, legal, sponsorship, compensation, and salary questions remained human-controlled. The no-write pilot did not answer or submit any such questions.

## Remaining blockers

The remaining execution blockers are operational rather than provider availability. First, the Notion connector is still disabled or unavailable for this session, so no Review, Resume Library, or Applications records could be synchronized. Second, the authorized browser connector is disabled, so browser-side application execution cannot be performed. Third, four pilot jobs exceeded the bounded 180-second per-job processing limit and require a rerun with a longer allowance or a faster, less latency-sensitive orchestration path. Finally, xAI challenger review remains unavailable until an authorized `XAI_API_KEY` is configured.

Because there were no `AUTO_APPLY` results and no authorized browser session, **no application was opened, completed, or submitted**.

## Artifacts

The auditable outputs are `pilot/pilot_jobs.json`, `pilot/pilot_results.json`, `pilot/pilot_summary.json`, and `pilot/pilot_manus_run.log`. The provider smoke script is `pilot/smoke_manus.py`.

## Commit

The final commit identifier is provided in the completion message accompanying this report.
