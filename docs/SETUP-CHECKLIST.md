# Career OS — setup checklist

The code side is ready. Account-level secrets, Notion permissions, and the explicit browser-execution authorization remain required.

## GitHub repository secrets

Add these under **Settings → Secrets and variables → Actions → Repository secrets**:

- `GEMINI_API_KEY` (primary AI path used by workflows)
- `NOTION_TOKEN`
- `NOTION_REVIEW_QUEUE_PAGE_ID` (parent page under which review pages are created)
- `MANUS_API_KEY` (required for the Manus browser preflight/execution queue)
- `XAI_API_KEY` (optional — independent Grok challenger)

Never commit these values.

## Required repository variable for automatic browser execution

Under **Settings → Secrets and variables → Actions → Variables**:

- `CAREER_OS_EXECUTION_ENABLED` = `true` to permit the Manus browser queue to create tasks

The execution queue also uses these optional variables:

- `MANUS_BROWSER_AGENT_PROFILE` = `manus-1.6`
- `NOTION_APPLICATIONS_DATA_SOURCE_ID` = `a6925702-0d2a-4d68-919b-3401e1d8ff75`
- `NOTION_VERSION` = `2026-03-11`
- `GEMINI_MODEL` = `gemini-3.1-flash-lite`
- `GITHUB_MODEL` = `openai/gpt-4.1`
- `GROK_MODEL` = `grok-4.5`
- `NOTION_RESUME_LIBRARY_DATA_SOURCE_ID` = `3ac8bc1d-ce0e-8051-a553-000bb5f58abe`

## Notion permission (critical)

1. Create an internal Notion integration and copy its token into `NOTION_TOKEN`.
2. Share the **Career OS** root page (and specifically the review-queue parent page) with that integration (Invite → the integration).
3. Share the **Resume Library** database with the same integration.
4. Share the **Applications** database with the same integration so the browser lifecycle can repair missing Application records after transient intake failures.
5. Set `NOTION_REVIEW_QUEUE_PAGE_ID` to the page ID of the parent under which `… — REVIEW` pages should appear.

Without explicit share, the Actions runtime can get 404/unauthorized even if this ChatGPT connector can access the workspace.

## Automatic application lifecycle

A job being marked **Ready to Apply** in the canonical Jobs database is an eligibility signal, not proof that the browser may submit immediately. The automatic path is:

`Jobs Ready to Apply → persisted pipeline result → durable Applications record → Manus preflight → verified AUTO_APPLY manifest → Manus browser execution → employer/ATS confirmation → Applied`

If a pipeline run produced the full package but failed to create its Applications page, the browser lifecycle now attempts an idempotent repair before creating any Manus task. Recovery requires an exact role-specific job URL; it never guesses or creates an ambiguous application record.

The browser queue runs automatically after trusted intake workflows and also polls every 10 minutes for retained lifecycle state.

## Safety gates

Career OS never infers **Applied** from a task completion, resume upload, or browser navigation. Applied requires authoritative employer/ATS/LinkedIn confirmation evidence. CAPTCHA, OTP/MFA, identity verification, assessments, sensitive/legal questions, compensation decisions, unknown mandatory questions, suspicious redirects, and other human-controlled steps remain hard stops.

## First real test

1. Add a vacancy using the browser extension or a trusted intake source.
2. Confirm the pipeline produces a complete tailored resume and quality/ATS/recruiter gates pass.
3. Confirm a durable Applications record exists; if the initial Notion write fails, the Manus lifecycle should repair it on its next run.
4. Confirm the browser preflight task is created and remains inspection-only until all browser facts are verified.
5. If preflight returns `AUTO_APPLY_READY`, confirm the execution manifest is created and dispatched.
6. Confirm the final status changes to `Applied` only after employer/ATS/LinkedIn confirmation evidence is observed.

## Operating rule

Standing `AUTO_APPLY` authorization permits the Manus browser executor to submit only when the deterministic Career OS package, mandatory review gates, exact tailored-resume attachment, approved answers, live application flow, and all submission-safety conditions pass. Human-controlled blockers always stop execution.
