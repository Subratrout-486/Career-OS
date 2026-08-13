# Career OS — setup checklist

The code side is ready. Only account-level secrets and Notion permissions remain.

## GitHub repository secrets

Add these under **Settings → Secrets and variables → Actions → Repository secrets**:

- `GEMINI_API_KEY` (primary AI path used by workflows)
- `NOTION_TOKEN`
- `NOTION_REVIEW_QUEUE_PAGE_ID` (parent page under which review pages are created)
- `XAI_API_KEY` (optional — independent Grok challenger)

Never commit these values.

## Optional repository variables

Under **Settings → Secrets and variables → Actions → Variables**:

- `GEMINI_MODEL` = `gemini-3.1-flash-lite`
- `GITHUB_MODEL` = `openai/gpt-4.1`
- `GROK_MODEL` = `grok-4.5`
- `NOTION_RESUME_LIBRARY_DATA_SOURCE_ID` = `3ac8bc1d-ce0e-8051-a553-000bb5f58abe`
- `NOTION_VERSION` = `2026-03-11`

The workflows already have sensible defaults; variables are optional overrides.

## Notion permission (critical)

1. Create an internal Notion integration and copy its token into `NOTION_TOKEN`.
2. Share the **Career OS** root page (and specifically the review-queue parent page) with that integration (Invite → the integration).
3. Share the **Resume Library** database with the same integration.
4. Set `NOTION_REVIEW_QUEUE_PAGE_ID` to the page ID of the parent under which `… — REVIEW` pages should appear.

Without explicit share, the Actions runtime will get 404/unauthorized even if this chat connector works.

## First real test

1. Add a vacancy as `jobs/<name>.json` using `examples/job.json` (or use the browser extension).
2. Commit it, or open an issue with the `CAREER_OS_JOB_V1` payload as the repository owner.
3. Open **Actions → Career OS — Process Job** (or the intake workflow) and confirm the run succeeds.
4. Open the generated Notion review page and Resume Library entry.
5. Confirm the PDF/DOCX resume files are attached and downloadable.
6. Review fit, resume, unsupported-claim check, and challenger notes.
7. Apply manually only after approval.

## Operating rule

Career OS never auto-submits applications. Discovery is an input layer; the review and submission decision remains human-controlled.
