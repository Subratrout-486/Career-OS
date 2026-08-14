# Manus Browser Preflight → Verified AUTO_APPLY → Reconciliation

This runbook describes the controlled browser lifecycle added for Issue #34. It is an **extension of**, not a replacement for, Career OS’s Truth Guard, ATS, recruiter/Gemini review, duplicate prevention, design QA, and human-control rules.

> A Manus task being created, opening a job page, or uploading a file is **not** an application. Career OS writes `Applied` only after structured proof of a real employer, ATS, or LinkedIn confirmation surface and proof that the exact JD-tailored resume was attached.

## Lifecycle

| Phase | Command / workflow phase | Permitted work | Required output | Stops safely when |
|---|---|---|---|---|
| 1. Pipeline | Existing ATS, Gmail, or authorized specialist-source intake | Creates the tailored resume and durable Notion records; applies all pre-browser quality gates | Full `pipeline_results/*-result.json` artifact | Job is inactive, Truth Guard or ATS/recruiter/Gemini/design QA fails, required persistence fails, or the package is otherwise ineligible |
| 2. Preflight start | `run_manus_browser_preflight.py start` / `preflight_start` | Opens an **inspection-only** Manus task | Durable `browser_execution_state.json` with a preflight task ID | A browser is unavailable, the result lacks durable IDs or exact resume evidence, or the package is `DO_NOT_APPLY` |
| 3. Preflight poll | `run_manus_browser_preflight.py poll` / `preflight_poll` | Reads structured form observations; does not submit | `browser_execution_manifest.json` only if all checks return `AUTO_APPLY` | CAPTCHA/OTP/MFA, identity check, assessment, sensitive or unknown question, mismatch with an approved answer, suspicious redirect, unresolved form, or failed exact-resume upload evidence |
| 4. Verified execution | `dispatch_manus_browser_tasks.py` / `dispatch` | Creates one constrained browser task from a verified manifest | Task ID in durable state and `browser_execution_results.json` | A manifest gate, resume hash, Gemini provenance, browser fact, or duplicate-state check fails |
| 5. Reconciliation | `reconcile_manus_browser_execution.py` / `reconcile` | Polls task output and updates the durable Application record | `browser_submission_reconciliation.json` | Confirmation or exact-resume proof is absent; the record remains `Review` |

## Exact JD-tailored resume and forced upload fallback

The preflight request hashes the current Career OS PDF (or its JD-specific DOCX fallback) before creating the task. Browser observations must report the exact selected filename and SHA-256. The execution prompt requires the browser to:

1. Attempt the normal upload of the attached JD-specific file.
2. If it does not visibly succeed, use the browser file chooser with that **same file**.
3. If necessary, retry the file input with that **same file**.
4. Verify the visible filename and required hash before continuing.

When normal upload fails, a later phase is eligible only if `file_chooser_retry_succeeded` or `input_retry_succeeded` is explicitly true. An attempted but unsuccessful fallback is a review blocker. Master, generic, or other-job resumes are never eligible substitutes.

## Approved required answers and the TCS Easy Apply case

Every required question must exactly match a user-approved question record. The browser cannot create, revise, or reinterpret an answer. The TCS Easy Apply regression fixture demonstrates the required behavior:

| Required question | Approved answer | Rule |
|---|---:|---|
| “How many years of engineering experience do you have?” | `0` | Technical-support experience is not recast as engineering experience. Any value other than the explicit approved `0` returns `REVIEW_REQUIRED`. |

Unknown, conflicting, unapproved, or merely inferred answers are persisted as feedback for the Application Questions workflow and block execution.

## Evidence required for `Applied`

The reconciler accepts `Applied` only when all of the following are true:

- `status` is `SUBMITTED` and `submitted` is true.
- `confirmation_source` is one of `employer`, `ats`, or `linkedin`.
- A non-empty `confirmation_evidence` and a confirmation URL are provided.
- The executor verified the visible resume attachment and exact SHA-256.
- The selected hash is the manifest’s exact resume hash.
- The normal upload succeeded or, after normal failure, the file chooser or input fallback explicitly succeeded.
- No human-controlled or other structured blockers remain.

Every other result, including a successful agent task, navigation completion, a non-submitting upload, or missing confirmation evidence, is persisted as `Review` with its blockers.

## Workflow entrypoints and artifact handoff

The following workflows now retain full pipeline-result artifacts for this lifecycle:

- **Career OS — Job Discovery** (employer ATS)
- **Career OS — Gmail Job Intake**
- **Career OS — Specialist Source Intake** (authorized Jobright/Simplify captures only)

Download the relevant pipeline-result artifact, stage it along with its exact resume artifact and any approved Application Questions export, then invoke **Career OS — Manus Browser Execution** phase by phase. Preserve the emitted `browser_execution_state.json` between phases. The state store reserves each stage by durable Application ID, URL, and exact resume hash; it skips a rerun with the same fingerprint and blocks automatic reuse if the fingerprint changes.

> The lifecycle assumes no undocumented Jobright or Simplify APIs. Those sources remain user-authorized browser-capture or export inputs only.
