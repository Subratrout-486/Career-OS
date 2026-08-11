# Career OS — final setup checklist

The code side is ready. Only account-level secrets and Notion permissions remain.

## GitHub repository secrets

Add these under **Settings → Secrets and variables → Actions → Repository secrets**:

- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `XAI_API_KEY`
- `NOTION_TOKEN`
- `NOTION_REVIEW_QUEUE_PAGE_ID`

Never commit these values.

## Optional repository variables

Under **Settings → Secrets and variables → Actions → Variables**:

- `OPENAI_MODEL` = `gpt-5.6`
- `CLAUDE_MODEL` = `claude-sonnet-4-5`
- `GROK_MODEL` = `grok-4.5`

The workflow already has these defaults, so variables are optional.

## Notion permission

The Career OS internal connection must be explicitly shared with the parent **Career OS review queue** page. The value used as `NOTION_REVIEW_QUEUE_PAGE_ID` must be the ID of that accessible parent page.

## First real test

1. Add a real vacancy as `jobs/<name>.json` using `examples/job.json`.
2. Commit it to `main`.
3. Open **Actions → Career OS — Process Job → Run workflow**.
4. Select the job JSON path.
5. Confirm the run succeeds.
6. Open the generated Notion review page.
7. Review the fit report, full tailored resume, unsupported-claim check and Grok challenge.
8. Apply manually only after approval.

## Operating rule

Career OS can discover/accept jobs from multiple sources, but it must not bypass site controls or perform unauthorized LinkedIn/Indeed scraping or automated Easy Apply clicks. Discovery is an input layer; the review/application decision remains human-controlled.
