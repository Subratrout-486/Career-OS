# Career-OS

Personal AI Career Operating System.

## Live workflow

`Job Capture → JD/Fit → JD-specific Resume → Independent Challenge → Notion Review → Human Approval → Application → Tracking`

## Current architecture

- **JD/Fit + Resume + Challenger runtime:** Career OS agent runtime using the configured AI provider (the live GitHub workflow currently uses Gemini plus GitHub Models configuration).
- **Review Queue:** Notion API.
- **Job Capture:** Career OS Chrome extension → GitHub issue intake → GitHub Actions.
- **Application:** Human-approved application using the source site, Simplify or Huntr.
- **Tracking:** Notion + Huntr.

Discovery tools remain sources/inputs; Career OS does not bypass their access controls.

## Human approval rule

Career OS does **not** auto-submit applications. A role must reach `READY_FOR_REVIEW`, and the user reviews the job, fit report, challenger notes and JD-specific resume before applying.

## Fast path: browser extension

The `extension/` folder contains a Manifest V3 Chrome extension. It captures the current job page, lets the user review/edit the extracted job data, opens a GitHub issue, and fills the complete machine-readable job payload into that issue. The user still clicks **Submit new issue**.

The `career-os-job-intake` workflow then extracts the payload, commits it under `jobs/inbox/`, runs the existing pipeline, uploads the generated resume artifacts, and comments the processing status on the issue.

### Install the extension

1. Clone/download the repository.
2. Open `chrome://extensions`.
3. Enable **Developer mode**.
4. Click **Load unpacked**.
5. Select the repository's `extension/` folder.
6. Pin **Career OS Job Capture**.

See `extension/README.md` for the detailed flow.

## Manual fallback

You can still create a JSON file under `jobs/` using the schema in `examples/job.json` and run **GitHub → Actions → Career OS — Process Job → Run workflow** with that path.

The workflow produces a JSON artifact and, when Notion credentials are configured, a full Notion review page plus resume-library entry.

## Required GitHub secrets

Repository → **Settings → Secrets and variables → Actions**:

- `GEMINI_API_KEY`
- `NOTION_TOKEN`
- `NOTION_REVIEW_QUEUE_PAGE_ID`

The workflow also uses the repository-provided `GITHUB_TOKEN`.

Optional GitHub Actions variables can override:

- `GITHUB_MODEL`
- `GEMINI_MODEL`
- `NOTION_RESUME_LIBRARY_DATA_SOURCE_ID`
- `NOTION_VERSION`

Never commit API keys.

## Review and apply

Open the generated Notion review page and review:

- job and source
- fit score, matches, gaps and blockers
- full JD-specific resume
- unsupported-claim check
- independent challenge notes

Then apply manually. Simplify/Huntr can be used at the application stage for autofill/tracking.

## Local setup

1. Copy `.env.example` to `.env`.
2. Keep `config/master_profile.md` as the approved source-of-truth evidence profile.
3. Install with `pip install -e .`.
4. Run:

```bash
career-os --profile config/master_profile.md --job-json examples/job.json
```

## Truthfulness rules

- No fabricated metrics.
- No invented certifications.
- No invented employers, dates, titles, degree, tools, responsibilities or production experience.
- Learning/lab exposure must not be silently converted into professional experience.
- If evidence is missing, flag it as a gap.
- A high ATS score never overrides factual accuracy.
