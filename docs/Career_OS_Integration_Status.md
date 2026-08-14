# Career OS Integration Status

**Status:** Implementation completed and regression-tested. The repository now supports a conservative, auditable handoff from an already-gated Career OS application record to a private Manus browser-execution task. No live application task was created, no browser was attached, and no application was submitted during this implementation.

## Implemented workflow changes

| Area | Implemented behavior | Safety effect |
|---|---|---|
| Resume design QA | `design_qa.py` checks the exact PDF and DOCX artifacts for a one-page PDF, conventional ATS headings, broken characters, internal-generation labels, and a table-free DOCX layout. | A missing or noncompliant candidate-facing artifact cannot qualify for browser dispatch. |
| Gemini adversarial review | The challenger uses **Gemini exclusively** for the independent adversarial review and returns a structured `PASS`, `REVISE`, `BLOCKED`, or `NOT_RUN` result. No DeepSeek/xAI fallback is permitted. | An absent, failed, ambiguous, or non-Gemini review can never be represented as approval. |
| AUTO_APPLY gate | Browser eligibility now requires an explicit active-job signal, acceptable risk result, Manus `APPLY` and Gemini `APPLY` recommendations, Truth Guard pass, ATS pass, recruiter-review pass **with Gemini provenance**, design-QA pass, exact-resume hash verification, and verified browser/form/answer/resume facts. | The mode remains `REVIEW_REQUIRED` unless every deterministic prerequisite is present. |
| Browser task runner | `manus_browser_runner.py` uploads the exact current PDF/DOCX to the Manus Files API, verifies `status=uploaded`, and creates a private structured-output task with the verified job identity and resume attached. | The task cannot silently substitute a master, stale, or guessed resume. |
| Execution manifest | `scripts/dispatch_manus_browser_tasks.py` accepts only explicit manifest records carrying all gate evidence, a Gemini adversarial pass/provider, the exact artifact path, and a SHA-256 hash. | The dispatch script fails closed on an absent gate, missing Gemini provenance, human-controlled blocker, URL, record ID, artifact, or hash mismatch. |
| Browser-outcome reconciliation | `browser_outcomes.py`, `ApplicationsTracker.record_browser_outcome()`, and `scripts/reconcile_browser_outcomes.py` consume structured executor results. | `Applied` is written only for `SUBMITTED` + `submitted=true` + explicit employer/ATS confirmation evidence + no blockers; every other result remains `Review`. |
| GitHub workflow | The former scheduled issue-only queue is replaced by a manually dispatched `Career OS — Manus Browser Execution` workflow. It requires a verified manifest and opt-in secrets/variables, and retains results as an artifact. | It cannot auto-retry or fabricate a browser task from dashboard text alone. |

## Browser executor contract

The generated Manus task may use only the attached JD-specific resume and verified profile facts. It must pause rather than proceed on CAPTCHA, OTP/MFA, identity checks, assessments, salary/CTC, sponsorship or work-authorisation uncertainty, unknown required fields, a required custom cover letter, suspicious redirects, or any other judgement-dependent question.

> **An uploaded resume is not proof of submission.** The executor must verify the employer or ATS confirmation screen and return structured evidence before the application can be recorded as submitted.

## Validation

| Check | Result |
|---|---|
| Focused Gemini-gate, browser-dispatch, and outcome-reconciliation tests | Passed: 21 tests |
| Full project regression suite | Passed: 136 tests |
| Diff whitespace check | Passed |
| Live API/browser execution | Not run; intentionally blocked pending configured credentials, a verified manifest, and user-browser selection |

## Required configuration before the first live browser task

1. Enable and configure the **Google Gemini connector/API key**. Gemini is mandatory for the adversarial reviewer; without it, Career OS correctly stays out of `AUTO_APPLY`.
2. Add a `MANUS_API_KEY` repository secret with `create_task` scope.
3. Set the repository variable `CAREER_OS_EXECUTION_ENABLED` to `true`; it defaults to a safe no-op.
4. Optionally set `MANUS_BROWSER_AGENT_PROFILE`; the workflow defaults to `manus-1.6`.
5. Create a **verified browser-execution manifest**. Every record must contain the job URL and application ID, exact resume path and SHA-256 hash, active-job/risk evidence, explicit Manus and Gemini `APPLY` decisions, a Gemini-provider adversarial pass, Truth Guard/ATS/recruiter/design-QA passes, verified form/answer/attachment signals, and no human-controlled blockers.
6. Run the GitHub workflow manually and choose an authenticated user browser for the created task if execution reaches a live form.
7. Reconcile the task’s structured outcome with `scripts/reconcile_browser_outcomes.py`; sync `Applied` only when there is actual employer/ATS confirmation evidence.

This implementation deliberately does not create recurring unattended browser submissions. Discovery and analysis may continue on schedules, but live application execution remains a bounded, auditable, user-browser-mediated operation. The manual execution manifest is re-validated immediately before task creation, including the active employer/ATS posting, acceptable ghost-job risk, Manus and Gemini `APPLY` evidence, Truth Guard, quality gates, exact resume SHA-256, and the absence of human-controlled blockers.
