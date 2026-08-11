# Career-OS

Personal AI Career Operating System.

## Live architecture

`Discovery → JD/Fit → JD-specific Resume → Independent Challenge → Notion Review → Human Approval → Application → Tracking`

## Agents

- **JD/Fit Agent:** OpenAI Responses API
- **Resume Tailoring Agent:** Claude API
- **Independent Challenger:** Grok API
- **Review Queue:** Notion API adapter
- **Discovery:** Scout / Jobright / compliant LinkedIn job signals (inputs are accepted as job JSON)
- **Autofill:** Simplify remains a human-approved application-stage tool
- **Tracking:** Notion + Huntr

OpenAI's current agent platform is designed around models, tools and instructions, and the current Responses/Agents direction is the recommended path for new agent builds rather than the deprecated Assistants API. citeturn0search14turn0search2

Grok currently supports a Responses API, function calling and tool use, so it is implemented here as an independent challenger rather than a duplicate resume writer. citeturn0search3turn0search6

## Human approval rules

The system does **not** auto-submit applications. A job and its tailored resume must reach `READY_FOR_REVIEW`; the user decides whether to apply. LinkedIn automation is limited to compliant signals/alerts or user-provided jobs; no unauthorized scraping or automated Easy Apply clicking.

## Local setup

1. Copy `.env.example` to `.env` and add API keys.
2. Replace `config/master_profile.md` with the approved master resume/evidence profile.
3. Put a real job in `examples/job.json` (or pass another JSON file).
4. Install with `pip install -e .`.
5. Run:

```bash
career-os --profile config/master_profile.md --job-json examples/job.json
```

If `NOTION_TOKEN` and `NOTION_REVIEW_QUEUE_PAGE_ID` are configured, the pipeline creates a review page in Notion. Without them, it still runs the AI analysis locally and prints the structured result.

## Security

- Never commit `.env` or API keys.
- Keep the master resume/evidence data private.
- Never use an ATS score as permission to invent a claim.
