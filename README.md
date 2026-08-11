# Career-OS

Personal AI Career Operating System.

## Live workflow

`Discovery → JD/Fit → JD-specific Resume → Independent Challenge → Notion Review → Human Approval → Application → Tracking`

## AI departments

- **JD/Fit Agent:** OpenAI Responses API
- **Resume Tailoring Agent:** Claude API
- **Independent Challenger:** Grok Responses API
- **Review Queue:** Notion API
- **Discovery inputs:** Scout, Jobright, Simplify, Huntr, LinkedIn, Indeed, company career sites, and other permitted sources. Discovery tools remain sources/inputs; Career OS does not bypass their access controls.
- **Application:** Human-approved application using the source site, Simplify or Huntr
- **Tracking:** Notion + Huntr

## Human approval rule

Career OS does **not** auto-submit applications. A role must reach `READY_FOR_REVIEW`, and the user reviews the job, fit report, challenger notes and JD-specific resume before applying.

## Run a real job

### 1. Add the secrets in GitHub

Repository → **Settings → Secrets and variables → Actions**:

- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `XAI_API_KEY`
- `NOTION_TOKEN`
- `NOTION_REVIEW_QUEUE_PAGE_ID`

Optional GitHub Actions variables can override:

- `OPENAI_MODEL` (default `gpt-5.6`)
- `CLAUDE_MODEL` (default `claude-sonnet-4-5`)
- `GROK_MODEL` (default `grok-4.5`)

Never commit API keys.

### 2. Prepare a job

Create a JSON file under `jobs/` using the schema in `examples/job.json`. Paste the complete JD and include the source URL when available.

### 3. Run the pipeline

Go to **GitHub → Actions → Career OS — Process Job → Run workflow** and select the job JSON path.

The workflow runs the three AI departments and writes the full review package to Notion when the Notion credentials are configured. A JSON result is also saved as a GitHub Actions artifact.

### 4. Review and apply

Open the generated Notion review page. Review:

- job and source
- fit score, matches, gaps and blockers
- full JD-specific resume
- unsupported-claim check
- Grok's independent challenge

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
