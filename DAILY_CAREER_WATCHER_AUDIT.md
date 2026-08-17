# Daily Direct Company Career-Site Watcher — Implementation Audit

**Repository:** [Subratrout-486/Career-OS](https://github.com/Subratrout-486/Career-OS)  
**Branch:** `main`  
**Commit:** `e1a3ea0 Add daily official career site watcher`

## Architecture placement

The watcher is upstream of the existing `CareerOS.process` boundary. It does not introduce a second job database, matching engine, application workflow, or Notion pipeline. The existing `scripts/discover_jobs.py` entry point now combines its established Greenhouse/Lever discovery with direct official-career discovery, persists the same candidate JSON payloads, and continues to hand them to the existing orchestrator and `scripts/sync_job_to_notion.py` workflow.

The source registry is `config/company_watchlist.json`. The watcher implementation is `scripts/direct_career_watcher.py`. The canonical `career_os.models.Job` model now accepts the additional provenance, identity, freshness, status, and hash fields without breaking existing callers.

## Files changed

| File | Change |
|---|---|
| `config/company_watchlist.json` | Added the complete requested watchlist, canonical aliases, and only verified source URLs. Unverified entries remain intentionally unconfigured. |
| `scripts/direct_career_watcher.py` | Added bounded public-source fetching, retry/backoff, controlled batches, JSON-LD extraction, official Greenhouse JSON support, India/location filtering, normalization, hashes, source health, failure isolation, and daily digest generation. |
| `scripts/discover_jobs.py` | Extended the existing discovery entry point to consume direct-career candidates without creating a competing intake path. |
| `src/career_os/models.py` | Added watcher metadata fields to the existing `Job` contract. |
| `.github/workflows/job-discovery.yml` | Changed the schedule to 08:00 India time (`02:30 UTC`) and added watcher/config change triggers. |
| `tests/test_direct_career_watcher.py` | Added tests for normalization, official identity preservation, eligibility, failure isolation, and watchlist aliases. |

## Companies configured and verified

All **136 watchlist entries** are configured as monitored company records. Eleven official source URLs were verified with live HTTP requests during testing: Accenture, Amazon, Apple, Google, HighRadius, IBM, Microsoft, NVIDIA, Oracle, Salesforce, and ServiceNow. HighRadius additionally uses its public official Greenhouse JSON endpoint and produced **17 qualifying official job URLs** in the live run; all 17 were Hyderabad-relevant under the current location filter.

The remaining **125 companies** are recorded as `UNCONFIGURED` rather than being assigned guessed URLs. This is deliberate: the implementation never fabricates a career URL. The registry supports adding verified sources later without changing application logic.

## Special handling

The generic adapter reads public `JobPosting` JSON-LD from official career pages. HighRadius uses a dedicated public Greenhouse JSON adapter because its official source exposes structured job data through that endpoint. All other currently verified HTML sources returned HTTP 200 but did not expose public `JobPosting` JSON-LD in the fetched response, so they are reported as `AVAILABLE_NO_PUBLIC_JOBPOSTING_DATA` rather than generating incomplete jobs.

## Scheduler and execution

The existing GitHub Actions `job-discovery.yml` workflow remains the scheduler and execution boundary. It runs daily at 08:00 Asia/Kolkata, expressed as `30 2 * * *` because GitHub Actions cron uses UTC. The workflow retains concurrency control, runs companies in bounded batches, and continues through individual source failures. The existing downstream processing loop still invokes `career_os.orchestrator` followed by the canonical Notion sync script.

## Normalization and deduplication

Each candidate preserves `company`, `company_normalized`, `source_type`, `source_url`, `official_job_url`, `job_id`, title, location, timestamps, status, work mode, published date, content hash, source hash, and a stable deduplication key. Greenhouse identifiers are retained in the canonical URL so distinct postings are not collapsed. Existing GitHub issue URL checks and Notion URL-based update-or-create behavior remain in place downstream. The watcher also emits a daily digest containing company health and discovery counters.

The current workflow has no durable cross-run state store for historical `UPDATED` and `CLOSED` transitions. Therefore the implementation records the fields and statuses needed for those transitions and is safe to rerun at the intake boundary, but full historical closure confirmation requires the existing durable destination or a future persisted discovery-state store. No job is automatically marked closed after a single failed request.

## Matching and Notion/dashboard integration

The watcher stops after producing normalized `Job` payloads. The existing orchestrator continues to perform JD analysis, profile/resume matching, ATS checks, verification, recruiter review, and application-mode safety checks. The existing Notion sync continues to update or create the canonical Jobs data source by official job URL and writes the full fit audit. The static dashboard/API remains unchanged because discovery already reaches it through the existing pipeline state and Notion destination.

No automatic applications, recruiter messages, credential storage, cookie extraction, CAPTCHA bypass, private API access, or authentication bypass was added.

## Tests executed

The focused watcher, source-intake, and pipeline-contract tests passed: **10 passed**. The complete repository test suite passed: **228 passed, 1 warning**. Python compilation and `git diff --check` also passed. A live watcher run checked all 136 registry entries, successfully reached 11 configured official sources, recorded 125 unconfigured/inaccessible entries, and discovered 17 qualifying HighRadius jobs with official URLs.

## Remaining limitations

The majority of the requested companies still require official URL verification and, where applicable, a company-specific parser or public ATS endpoint. Some official career sites render search results client-side or require interaction that is not available to a passive public fetch; those sources are correctly reported without invented jobs. Durable historical `UPDATED`/`CLOSED` state and a first-class dashboard digest view are not yet implemented beyond the emitted daily digest and existing downstream URL deduplication. Human approval remains required before any application action.

## References

[1]: https://github.com/Subratrout-486/Career-OS "Career OS repository"
[2]: https://github.com/Subratrout-486/Career-OS/commit/e1a3ea0 "Daily official career site watcher implementation commit"
