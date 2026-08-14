# Verified Browser Manifest and Specialist-Source Intake

## Purpose

Career OS separates **job discovery**, **decisioning**, **document preparation**, and **browser execution**. The browser executor receives a manifest only after the pipeline has reached `AUTO_APPLY` and every deterministic gate has been revalidated. A manifest is an execution package, not proof that an application was submitted. The existing outcome reconciler must still receive employer or ATS confirmation evidence before Notion is marked `Applied`.

## Browser execution manifest

The manifest generator is `career_os.browser_execution_manifest.generate_browser_execution_manifest`. It is also available through the orchestrator:

```bash
python -m career_os.orchestrator \
  --profile config/master_profile.md \
  --job-json jobs/example.json \
  --browser-context-json verified-browser-context.json \
  --result-output pipeline-result.json \
  --manifest-output browser_execution_manifest.json
```

The command emits a manifest only when the package is already `AUTO_APPLY`, has a durable Notion Application ID and Resume Library reference, and passes the following gates again at generation time.

| Gate | Required evidence |
|---|---|
| Job validity | `ACTIVE` job verification and acceptable ghost-job risk |
| Primary decision | Manus-provenance `APPLY` recommendation |
| Truthfulness | No Truth Guard error |
| Candidate artifacts | ATS, Gemini adversarial review, and deterministic design QA all pass |
| Browser facts | Verified URL, straightforward form, full form review, approved required answers, exact attachment, and exact SHA-256 |
| Human control | No CAPTCHA, OTP/MFA, identity, legal/sensitive, sponsorship, salary/CTC, assessment, unknown-field, relocation, or other human-controlled blocker |
| Tracking | Durable Notion Application and Resume Library records |

Each record includes the exact resume filename, SHA-256, runtime path, persistent Resume Library reference, application record ID, application method, all gate results, answer-approval status (but **never the answer text**), and an empty human-control blocker list. The dispatcher validates the generator schema and every gate again per record. A malformed record is reported as `BLOCKED`; sibling records can continue to be considered.

> **Important:** a runner-local path is retained only as the execution-time artifact reference. Notion’s `Resume Used` field continues to point to the persistent Resume Library page and never claims that a runner-local path is durable storage.

## Jobright and Simplify intake

The official Jobright autofill flow is browser-based: install its extension, configure a profile, open a job application site, click Autofill, and submit.[^jobright] The official Simplify Copilot flow similarly uses a configured profile and browser extension; Simplify lists supported portals and provides its own popup on compatible pages.[^simplify] The reviewed public product materials did **not** document a supported third-party API for direct account ingestion or application submission.

Career OS therefore supports these sources only as **user-authorized JSON exports or browser captures**. It does not scrape authenticated accounts, store user passwords, impersonate either platform, or claim an undocumented API connection.

```bash
python scripts/import_specialist_jobs.py \
  --source jobright \
  --input authorized-jobright-capture.json \
  --intake-method authorized_browser_capture \
  --output-dir jobs/discovery_runtime \
  --report jobright-intake-report.json
```

The input may be a JSON list or an object with a `jobs` list. Each record must contain a title, company, job/application URL, and job description. The importer retains source attribution and source job ID, removes common tracking parameters for comparison, calculates a canonical duplicate key, and only writes unique records. Every written record must still pass the normal Career OS verification, Truth Guard, reviewer, design-QA, browser, and submission-confirmation controls.

| Source | Supported Career OS intake | Account access | Application handling |
|---|---|---:|---|
| Jobright | Authorized JSON export or browser capture | Required in the user’s own browser | Supervised Jobright extension/browser workflow |
| Simplify | Authorized JSON export or browser capture | Required in the user’s own browser | Supervised Simplify Copilot/browser workflow |
| Employer ATS | Public ATS feed or authorized JSON export | Not required for public feeds | Employer application page, still subject to all gates |

## Required browser context

The authenticated browser adapter must produce only observed facts. It must not infer that an answer, attachment, or submission occurred. At minimum, a potential `AUTO_APPLY` context includes the following shape:

```json
{
  "application_type": "straightforward_form",
  "application_method": "external employer application",
  "application_url_verified": true,
  "complete_form_verified": true,
  "required_answers_verified": true,
  "resume_attachment_verified": true,
  "resume_sha256_verified": true
}
```

Any human-controlled flag, including `captcha`, `otp`, `mfa`, `identity_verification`, `unknown_required_question`, `salary_or_ctc_question`, `sponsorship_or_authorization_ambiguity`, `unsupported_experience_question`, or `suspicious_redirect`, prevents manifest generation. When a platform extension surfaces a field it cannot safely map from user-approved profile data, the browser adapter must set the relevant blocker and return the package to review.

[^jobright]: [Jobright, “Autofill Job Applications With 1-Click”](https://jobright.ai/job-autofill), reviewed 2026-08-14.
[^simplify]: [Simplify, “Autofill Job Applications and Track Jobs”](https://simplify.jobs/copilot), reviewed 2026-08-14.
