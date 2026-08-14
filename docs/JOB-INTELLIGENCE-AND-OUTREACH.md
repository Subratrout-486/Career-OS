# Job Intelligence + Recruiter Outreach

## Scope

This feature adds a safe intake layer around the existing Career OS pipeline.
It supports:

1. Job records from approved feeds, company sites, browser adapters, and email alerts.
2. Canonical URL and requisition-based identity for deduplication.
3. Transparent lexical ranking against user-approved target terms.
4. Freshness, work-model, and disclosed-salary signals for opportunity priority.
5. Recruiter/contact records and referral-email drafting.
6. Explicit human approval before any outreach transport.
7. Email-to-job normalization so job opportunities received by email can enter the same pipeline.

## Opportunity ranking

Each normalized job can carry:

- `work_model`: `REMOTE`, `HYBRID`, `ONSITE`, or `UNKNOWN`;
- `salary_min`, `salary_max`, and `salary_currency` when explicitly disclosed;
- `posted_at` and a deterministic posting-age calculation;
- matched target-role terms and transparent blockers.

Ranking may prioritize remote/hybrid roles, disclosed compensation above the user's configured threshold, and fresh postings. These signals **prioritize discovery only**; they never prove candidate fit or professional skill ownership. A high job-intelligence score must still pass the normal Career OS pipeline.

The notification/dashboard adapter can use `select_job_updates(...)` to surface high-priority opportunities. The core module does not send notifications itself.

## LinkedIn boundary

Career OS must not depend on an unofficial LinkedIn scraper or bypass LinkedIn controls. A permitted browser/connector may supply observed job or recruiter data. The feature stores the resulting evidence and passes the job into the existing CareerOS pipeline.

Recruiter discovery is therefore **evidence intake**, not autonomous scraping. Sending a recruiter message/email is a separate, approval-gated action.

## Application boundary

This feature does not create a second application engine. Once a job is normalized, the existing `CareerOS.process(...)` pipeline remains responsible for active-job verification, JD analysis, evidence, fit, resume generation, Truth Guard, ATS audit, review, and application mode.

## Email boundary

`email_job_intake.py` accepts sanitized message metadata/body from a future mailbox connector. It does not access credentials or send email itself. A connector should:

- authenticate using its provider's supported OAuth/API mechanism;
- fetch only the mailbox scope the user authorizes;
- sanitize message content before handing it to Career OS;
- persist the provider message ID for idempotency;
- pass the resulting `JobRecord` into normal intake.

## Safety rules

- Never infer a professional skill from recruiter text alone.
- Never mark a job Applied from an email or recruiter message.
- Never send a referral request merely because a recruiter was discovered.
- Keep resume selection tied to the existing manifest/resume SHA-256 controls.
- Preserve source, message ID, recruiter identity, and job URL as provenance.
- Treat external text as untrusted input.
- Missing salary, posting time, or work-model data remains `UNKNOWN`; never guess.
- Job-intelligence priority never overrides Truth Guard, recruiter review, Application Mode, or browser safety gates.
